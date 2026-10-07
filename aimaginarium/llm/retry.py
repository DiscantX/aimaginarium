"""Retry with backoff, as a wrapper that works with any provider."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Optional

from .base import (
    Capabilities, Chunk, LLMProvider, ProviderUnavailableError, Request, RetryableError, StreamEvent,
)


@dataclass(frozen=True)
class RetryPolicy:
    """How long and how often to retry a busy provider.

    Attributes:
        attempts: Maximum calls, including the first.
        base_delay: Seconds to wait after the first failure; doubles each time.
        max_delay: Longest single wait, in seconds.
        max_total_wait: Give up rather than wait longer than this in total.
        jitter: Random spread applied to each wait (0.25 means plus or minus 25%).
    """

    attempts: int = 6
    base_delay: float = 1.0
    max_delay: float = 20.0
    max_total_wait: float = 45.0
    jitter: float = 0.25

    def delay(self, attempt: int, waited: float, error: RetryableError) -> Optional[float]:
        """Chooses the wait before the next attempt.

        Args:
            attempt: The attempt that just failed, starting at 1.
            waited: Seconds already spent waiting.
            error: The failure; its ``retry_after`` is used if the server gave one.

        Returns:
            Seconds to wait, or None if the wait would exceed the limits.
        """
        if error.retry_after is not None:
            if error.retry_after > self.max_delay:
                return None
            wait = error.retry_after
        else:
            wait = min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
            wait *= 1 + random.uniform(-self.jitter, self.jitter)
        return None if waited + wait > self.max_total_wait else wait


@dataclass(frozen=True)
class RetryNotice:
    """Passed to the ``on_retry`` callback so a client can tell the player.

    Attributes:
        attempt: The attempt that just failed, starting at 1.
        delay: Seconds until the next attempt.
        error: The failure.
    """

    attempt: int
    delay: float
    error: RetryableError


class RetryingProvider(LLMProvider):
    """Wraps a provider and retries calls that fail with :class:`RetryableError`.

    A call is only retried if it failed before any text reached the caller;
    once text has been streamed, the error is raised as it is.
    """

    def __init__(
        self,
        inner: LLMProvider,
        policy: RetryPolicy = RetryPolicy(),
        on_retry: Optional[Callable[[RetryNotice], None]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """Initialises the wrapper.

        Args:
            inner: The provider to protect.
            policy: How long and how often to retry.
            on_retry: Called before each wait, for progress messages.
            sleep: Awaitable sleep function (replaceable in tests).
        """
        self.inner = inner
        self.policy = policy
        self._on_retry = on_retry
        self._sleep = sleep

    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Returns the wrapped provider's capabilities."""
        return self.inner.capabilities(model)

    async def aclose(self) -> None:
        """Closes the wrapped provider if it has anything to close."""
        close = getattr(self.inner, "aclose", None)
        if close:
            await close()

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams from the wrapped provider, retrying early failures.

        Raises:
            ProviderUnavailableError: If the policy's limits are reached.
            RetryableError: If the failure came after text was already streamed.
        """
        waited = 0.0
        for attempt in range(1, self.policy.attempts + 1):
            streamed = False
            try:
                async for event in self.inner.stream(request):
                    streamed = streamed or isinstance(event, Chunk)
                    yield event
                return
            except RetryableError as exc:
                if streamed:
                    raise
                delay = None if attempt == self.policy.attempts else self.policy.delay(attempt, waited, exc)
                if delay is None:
                    raise ProviderUnavailableError(
                        f"provider unavailable after {attempt} attempts and {waited:.0f}s of waiting: {exc}",
                        attempts=attempt,
                        waited=waited,
                    ) from exc
                if self._on_retry:
                    self._on_retry(RetryNotice(attempt, delay, exc))
                await self._sleep(delay)
                waited += delay
