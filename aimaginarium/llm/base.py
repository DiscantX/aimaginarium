"""Provider-neutral types and the interface every LLM provider implements.

The engine talks only to :class:`LLMProvider`. Providers are stateless: each
call carries everything the model needs. Put stable content first in the
system prompt and messages, because providers cache by prefix.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional, Union

from pydantic import BaseModel

Role = Literal["user", "assistant"]


class ProviderError(Exception):
    """A provider call failed."""


class RetryableError(ProviderError):
    """A provider call failed in a way that may succeed if repeated (timeout, rate limit)."""


@dataclass(frozen=True)
class Message:
    """One conversation turn.

    Attributes:
        role: Either ``"user"`` or ``"assistant"``.
        content: The text of the turn.
    """

    role: Role
    content: str


@dataclass(frozen=True)
class Capabilities:
    """What a provider can do with a given model.

    Attributes:
        schema_enforcement: Output is constrained to a full JSON schema.
        json_mode: Output is constrained to valid JSON, with no schema.
        reports_cache: Usage includes a cached token count.
        tool_calling: The model supports function calling.
    """

    schema_enforcement: bool = False
    json_mode: bool = False
    reports_cache: bool = False
    tool_calling: bool = False


@dataclass(frozen=True)
class Request:
    """One stateless model call.

    Attributes:
        system: System prompt, stable content first.
        messages: Conversation so far, oldest first.
        model: Model name, or None for the provider default.
        schema: Pydantic model the reply must match, if any.
        temperature: Sampling temperature, or None for the provider default.
    """

    system: str = ""
    messages: tuple[Message, ...] = ()
    model: Optional[str] = None
    schema: Optional[type[BaseModel]] = None
    temperature: Optional[float] = None


@dataclass(frozen=True)
class Usage:
    """Token and timing figures for one call.

    Attributes:
        prompt_tokens: Tokens in the prompt.
        cached_tokens: Prompt tokens read from cache, or None if the provider
            cannot report it.
        output_tokens: Tokens generated.
        latency: Seconds from request to the end of the reply.
    """

    prompt_tokens: int = 0
    cached_tokens: Optional[int] = None
    output_tokens: int = 0
    latency: float = 0.0


@dataclass(frozen=True)
class Response:
    """A complete model reply.

    Attributes:
        text: The full reply text.
        model: The model that produced it.
        usage: Token and timing figures.
    """

    text: str
    model: str
    usage: Usage = Usage()


@dataclass(frozen=True)
class Chunk:
    """A piece of reply text received while streaming."""

    text: str


StreamEvent = Union[Chunk, Response]


class LLMProvider(ABC):
    """Interface implemented by every provider (Gemini, Ollama, ...)."""

    @abstractmethod
    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Describes what this provider can do with a model.

        Args:
            model: Model name, or None for the provider default.

        Returns:
            The capabilities of that model.
        """

    @abstractmethod
    def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Runs a request and yields the reply as it arrives.

        Args:
            request: The call to make.

        Yields:
            Zero or more :class:`Chunk` items, then exactly one :class:`Response`.

        Raises:
            ProviderError: If the call fails.
        """

    async def generate(self, request: Request) -> Response:
        """Runs a request and returns the complete reply.

        Args:
            request: The call to make.

        Returns:
            The final response.

        Raises:
            ProviderError: If the call fails or the stream has no final response.
        """
        final: Optional[Response] = None
        async for event in self.stream(request):
            if isinstance(event, Response):
                final = event
        if final is None:
            raise ProviderError("stream ended without a final response")
        return final
