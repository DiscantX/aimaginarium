"""Ollama provider, talking to the HTTP API directly.

The official Python SDK drops fields such as ``prompt_eval_cached_count``, so
the HTTP API is used instead.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Optional

import httpx

from ..base import (
    Capabilities, Chunk, LLMProvider, ProviderError, Request, Response, RetryableError, StreamEvent, Usage, ResponseTimer,
)

DEFAULT_CAPABILITIES = Capabilities(schema_enforcement=True, json_mode=True, reports_cache=True)


class OllamaProvider(LLMProvider):
    """Runs requests against a local or remote Ollama server.

    Attributes:
        base_url: Address of the Ollama server.
        default_model: Model used when a request names none.
    """

    def __init__(
        self,
        default_model: str,
        base_url: str = "http://localhost:11434",
        options: Optional[dict[str, Any]] = None,
        capabilities: Optional[dict[str, Capabilities]] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 300.0,
    ):
        """Initialises the provider.

        Args:
            default_model: Model used when a request names none.
            base_url: Address of the Ollama server.
            options: Ollama options sent with every request, such as ``num_ctx`` or ``num_thread``.
            capabilities: Per-model overrides of :data:`DEFAULT_CAPABILITIES`.
            client: HTTP client to use; one is created if omitted.
            timeout: Seconds to wait between bytes from the server.
        """
        self.default_model = default_model
        self.base_url = base_url
        self._options = dict(options or {})
        self._capabilities = capabilities or {}
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        """Closes the HTTP client."""
        await self._client.aclose()

    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Returns the override for ``model`` if given, else the defaults."""
        return self._capabilities.get(model or self.default_model, DEFAULT_CAPABILITIES)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams a chat completion.

        Args:
            request: The call to make.

        Yields:
            :class:`Chunk` items, then one :class:`Response`.

        Raises:
            RetryableError: On connection problems, timeouts, 429 and 5xx replies.
            ProviderError: On other HTTP errors or a malformed stream.
        """
        model = request.model or self.default_model
        timer = ResponseTimer()
        text: list[str] = []
        final: dict = {}
        try:
            async with self._client.stream("POST", "/api/chat", json=self._payload(request, model)) as http:
                if http.status_code != 200:
                    raise _http_error(http.status_code, (await http.aread()).decode(errors="replace"))
                async for line in http.aiter_lines():
                    if not line.strip():
                        continue
                    part = json.loads(line)
                    if "error" in part:
                        raise ProviderError(part["error"])
                    piece = part.get("message", {}).get("content", "")
                    if piece:
                        timer.record_chunk()
                        text.append(piece)
                        yield Chunk(piece)
                    if part.get("done"):
                        final = part
        except httpx.TransportError as exc:
            raise RetryableError(f"cannot reach Ollama at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"malformed stream from Ollama: {exc}") from exc
        if not final:
            raise ProviderError("Ollama stream ended before the final message")
        usage = Usage(
            prompt_tokens=final.get("prompt_eval_count", 0),
            cached_tokens=final.get("prompt_eval_cached_count"),
            output_tokens=final.get("eval_count", 0),
            latency=timer.latency(),
            time_to_first_token=timer.time_to_first_token,
        )
        yield Response("".join(text), final.get("model", model), usage)

    def _payload(self, request: Request, model: str) -> dict:
        """Builds the JSON body for ``/api/chat``."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})
        options = dict(self._options)
        if request.temperature is not None:
            options["temperature"] = request.temperature
        payload: dict = {"model": model, "messages": messages, "stream": True, "options": options}
        caps = self.capabilities(model)
        if request.schema is not None and caps.schema_enforcement:
            payload["format"] = request.schema.model_json_schema()
        elif request.schema is not None and caps.json_mode:
            payload["format"] = "json"
        return payload


def _http_error(status: int, body: str) -> ProviderError:
    """Maps an HTTP error status to a retryable or permanent error."""
    message = f"Ollama returned {status}: {body[:300]}"
    return RetryableError(message) if status == 429 or status >= 500 else ProviderError(message)
