"""A scripted provider for tests and for running the engine without a model."""

from __future__ import annotations

from typing import AsyncIterator, Iterable, Optional, Union

from ..base import Capabilities, Chunk, LLMProvider, Request, Response, StreamEvent, Usage


class FakeProvider(LLMProvider):
    """Replies with canned text, in order, and records every request.

    Attributes:
        requests: Every request received, oldest first.
    """

    def __init__(
        self,
        replies: Iterable[Union[str, Exception]],
        capabilities: Capabilities = Capabilities(schema_enforcement=True),
        chunk_size: int = 8,
    ):
        """Initialises the provider.

        Args:
            replies: Reply texts to return in order. An exception is raised instead.
            capabilities: Capabilities to report for every model.
            chunk_size: Characters per streamed chunk.
        """
        self._replies = iter(replies)
        self._capabilities = capabilities
        self._chunk_size = chunk_size
        self.requests: list[Request] = []

    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Returns the capabilities given at construction."""
        return self._capabilities

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams the next scripted reply.

        Raises:
            Exception: Whatever the script holds for this call.
            RuntimeError: If the script has run out of replies.
        """
        self.requests.append(request)
        reply = next(self._replies, None)
        if reply is None:
            raise RuntimeError("FakeProvider has no more scripted replies")
        if isinstance(reply, Exception):
            raise reply
        for start in range(0, len(reply), self._chunk_size):
            yield Chunk(reply[start : start + self._chunk_size])
        yield Response(reply, request.model or "fake", Usage(output_tokens=len(reply.split())))
