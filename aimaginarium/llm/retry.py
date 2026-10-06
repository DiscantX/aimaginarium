"""Retry with exponential backoff for provider calls."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from .base import RetryableError

T = TypeVar("T")


async def retry(call: Callable[[], Awaitable[T]], attempts: int = 3, backoff: float = 0.5) -> T:
    """Awaits ``call()``, repeating it when it raises :class:`RetryableError`.

    Wrap whole requests, not streams that have already started yielding.

    Args:
        call: Zero-argument factory returning a fresh awaitable on each attempt.
        attempts: Maximum number of attempts.
        backoff: Seconds to wait after the first failure; doubles each time.

    Returns:
        The result of the first successful attempt.

    Raises:
        RetryableError: If every attempt fails.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except RetryableError:
            if attempt == attempts:
                raise
            await asyncio.sleep(backoff * 2 ** (attempt - 1))
    raise AssertionError("unreachable")
