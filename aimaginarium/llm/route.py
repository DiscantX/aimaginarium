"""A task's route: an ordered list of provider and model candidates with fallback.

A route tries its candidates in order. It moves on only when a candidate is
unavailable (its :class:`RetryingProvider` gave up before any text reached the
caller), so nothing has been committed and no text has been shown. A candidate
that was unavailable is skipped for a cool-down window, so a dead primary does
not cost its whole retry budget on every call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import AsyncIterator, Callable, Optional, TypeVar

from pydantic import BaseModel

from .base import Chunk, LLMProvider, ProviderUnavailableError, Request, Response, StreamEvent
from .structured import StructuredCaller, StructuredOutputError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Candidate:
    """One provider and model a route can use.

    Attributes:
        name: The provider's configured name.
        provider: The provider to call.
        model: The model to ask it for.
    """

    name: str
    provider: LLMProvider
    model: str

    @property
    def label(self) -> str:
        """Returns ``provider:model``, for messages and the cool-down."""
        return f"{self.name}:{self.model}"


@dataclass(frozen=True)
class FallbackNotice:
    """Passed to the ``on_fallback`` callback so a client can tell the player.

    Attributes:
        task: The task being routed.
        failed: Label of the candidate that failed.
        next: Label of the candidate tried next.
        error: Why the candidate failed.
    """

    task: str
    failed: str
    next: str
    error: Exception


class Cooldown:
    """Remembers which candidates were recently unavailable."""

    def __init__(self, seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        """Initialises the tracker.

        Args:
            seconds: How long a failed candidate is skipped.
            clock: Monotonic time source (replaceable in tests).
        """
        self.seconds = seconds
        self._clock = clock
        self._until: dict[str, float] = {}

    def mark(self, label: str) -> None:
        """Starts the cool-down for a candidate."""
        self._until[label] = self._clock() + self.seconds

    def clear(self, label: str) -> None:
        """Ends the cool-down for a candidate, after it worked."""
        self._until.pop(label, None)

    def active(self, label: str) -> bool:
        """Returns whether the candidate is still being skipped."""
        return self._until.get(label, 0.0) > self._clock()


class Route:
    """The candidates for one task, tried in order.

    ``provider`` and ``model`` describe the primary candidate.
    """

    def __init__(
        self,
        candidates: list[Candidate],
        task: str = "",
        cooldown: Optional[Cooldown] = None,
        on_fallback: Optional[Callable[[FallbackNotice], None]] = None,
    ):
        """Initialises the route.

        Args:
            candidates: Primary first, then fallbacks. Must not be empty.
            task: The task name, for notices.
            cooldown: Shared cool-down tracker; a private one is used if omitted.
            on_fallback: Called when moving on from a failed candidate.
        """
        self.candidates = tuple(candidates)
        self.task = task
        self._cooldown = cooldown or Cooldown()
        self._on_fallback = on_fallback

    @property
    def provider(self) -> LLMProvider:
        """Returns the primary candidate's provider."""
        return self.candidates[0].provider

    @property
    def model(self) -> str:
        """Returns the primary candidate's model."""
        return self.candidates[0].model

    def with_model(self, request: Request) -> Request:
        """Returns ``request`` addressed to the primary candidate's model."""
        return replace(request, model=self.model)

    def _order(self) -> list[Candidate]:
        """Returns the candidates to try now: those not cooling down, or all if every one is."""
        ready = [c for c in self.candidates if not self._cooldown.active(c.label)]
        return ready or list(self.candidates)

    def _failed(self, order: list[Candidate], index: int, error: Exception, cool: bool) -> None:
        """Records a failure and notifies the client if another candidate follows."""
        failed = order[index]
        if cool:
            self._cooldown.mark(failed.label)
        if index + 1 < len(order) and self._on_fallback:
            self._on_fallback(FallbackNotice(self.task, failed.label, order[index + 1].label, error))

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams from the first candidate that is available.

        Args:
            request: The call to make; its model is replaced per candidate.

        Yields:
            Chunks, then the final response.

        Raises:
            ProviderUnavailableError: If every candidate is unavailable.
        """
        order = self._order()
        last: Optional[ProviderUnavailableError] = None
        for index, candidate in enumerate(order):
            streamed = False
            try:
                async for event in candidate.provider.stream(replace(request, model=candidate.model)):
                    streamed = streamed or isinstance(event, Chunk)
                    yield event
                self._cooldown.clear(candidate.label)
                return
            except ProviderUnavailableError as exc:
                if streamed:
                    raise
                last = exc
                self._failed(order, index, exc, cool=True)
        raise ProviderUnavailableError(
            f"every provider for task {self.task!r} is unavailable: {last}",
            attempts=sum(1 for _ in order),
            waited=0.0,
        ) from last

    async def generate(self, request: Request) -> Response:
        """Runs a request and returns the complete reply from the first available candidate."""
        final: Optional[Response] = None
        async for event in self.stream(request):
            if isinstance(event, Response):
                final = event
        if final is None:
            raise ProviderUnavailableError("stream ended without a final response", attempts=0, waited=0.0)
        return final

    async def call(self, request: Request, schema: type[T]) -> tuple[T, Response]:
        """Gets a validated object, moving to the next candidate if one cannot supply it.

        Capabilities differ per candidate, so each gets its own
        :class:`StructuredCaller`. A candidate is skipped when it is unavailable
        or never produces valid output; only unavailability starts a cool-down.

        Args:
            request: The call to make.
            schema: Pydantic model the reply must match.

        Returns:
            The validated object and the final response.

        Raises:
            ProviderUnavailableError: If every candidate was unavailable.
            StructuredOutputError: If the last candidate gave invalid output.
        """
        order = self._order()
        error: Optional[Exception] = None
        for index, candidate in enumerate(order):
            try:
                result = await StructuredCaller(candidate.provider).call(replace(request, model=candidate.model), schema)
                self._cooldown.clear(candidate.label)
                return result
            except ProviderUnavailableError as exc:
                error = exc
                self._failed(order, index, exc, cool=True)
            except StructuredOutputError as exc:
                error = exc
                self._failed(order, index, exc, cool=False)
        raise error  # type: ignore[misc]  # order is never empty
