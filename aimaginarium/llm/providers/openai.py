"""Base OpenAI provider implementation for OpenAI-compatible APIs.

Install the optional dependency with ``pip install "aimaginarium[zai]"`` (or similar).
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Optional

import httpx

try:
    from openai import APIError, APIConnectionError, RateLimitError, OpenAI
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise ImportError('The OpenAI-based provider needs the SDK: pip install "aimaginarium[zai]"') from exc

from ..base import (
    Capabilities, Chunk, LLMProvider, ProviderError, Request, Response, RetryableError, StreamEvent, Usage, ResponseTimer,
)

DEFAULT_CAPABILITIES = Capabilities(schema_enforcement=True, json_mode=True, tool_calling=True)


class OpenAIProvider(LLMProvider):
    """Runs requests against OpenAI-compatible APIs using the official ``openai`` SDK.

    Attributes:
        default_model: Model used when a request names none.
        base_url: API base URL.
    """

    def __init__(
        self,
        default_model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        capabilities: Optional[dict[str, Capabilities]] = None,
        client: Optional[Any] = None,
    ):
        """Initialises the provider.

        Args:
            default_model: Model used when a request names none.
            base_url: API base URL.
            api_key: API key; if omitted the SDK reads it from the environment.
            config: Extra kwargs or extra_body sent with every request.
            capabilities: Per-model overrides of :data:`DEFAULT_CAPABILITIES`.
            client: A ready ``OpenAI`` client (or test double); one is created if omitted.
        """
        self.default_model = default_model
        self.base_url = base_url
        self._config = dict(config or {})
        self._capabilities = capabilities or {}
        client_kwargs = {}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self._client = client or OpenAI(**client_kwargs)

    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Returns the override for ``model`` if given, else the defaults."""
        return self._capabilities.get(model or self.default_model, DEFAULT_CAPABILITIES)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams a chat completion request.

        Args:
            request: The call to make.

        Yields:
            :class:`Chunk` items, then one :class:`Response`.

        Raises:
            RetryableError: On connection problems, 429 and 5xx replies.
            ProviderError: On other API errors, or if the model returns no text.
        """
        model = request.model or self.default_model
        timer = ResponseTimer()
        text: list[str] = []
        usage = None
        try:
            payload = self._build_payload(request, model)
            # To be robust with both sync and async OpenAI clients (and test doubles):
            response = self._client.chat.completions.create(**payload)
            # If response is an async generator or iterable:
            if hasattr(response, "__aiter__"):
                async for chunk in response:
                    usage = getattr(chunk, "usage", usage)
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        reasoning = getattr(delta, "reasoning_content", None)
                        content = getattr(delta, "content", None)
                        piece = (reasoning or "") + (content or "")
                        if piece:
                            timer.record_chunk()
                            text.append(piece)
                            yield Chunk(piece)
            else:
                # Synchronous generator/iterable
                for chunk in response:
                    usage = getattr(chunk, "usage", usage)
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        reasoning = getattr(delta, "reasoning_content", None)
                        content = getattr(delta, "content", None)
                        piece = (reasoning or "") + (content or "")
                        if piece:
                            timer.record_chunk()
                            text.append(piece)
                            yield Chunk(piece)
        except APIError as exc:
            raise _api_error(exc) from exc
        except (APIConnectionError, httpx.TransportError) as exc:
            raise RetryableError(f"cannot reach OpenAI-compatible API: {exc}") from exc

        if not text:
            raise ProviderError("OpenAI-compatible API returned no text")
        
        final_usage = _usage(usage, timer)
        yield Response("".join(text), model, final_usage)

    def _build_payload(self, request: Request, model: str) -> dict[str, Any]:
        """Builds the payload for chat completions create."""
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            messages.append({"role": m.role, "content": m.content})
        
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            # Request usage in stream if supported by OpenAI API (stream_options={"include_usage": True})
            "stream_options": {"include_usage": True},
            **self._config,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        
        caps = self.capabilities(model)
        if request.schema is not None:
            if caps.schema_enforcement:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema.__name__,
                        "schema": request.schema.model_json_schema(),
                    },
                }
            elif caps.json_mode:
                payload["response_format"] = {"type": "json_object"}

        return payload


def _usage(meta: Any, timer: ResponseTimer) -> Usage:
    """Builds :class:`Usage` from OpenAI usage object."""
    if meta is None:
        return Usage(latency=timer.latency(), time_to_first_token=timer.time_to_first_token)
    return Usage(
        prompt_tokens=getattr(meta, "prompt_tokens", 0) or 0,
        cached_tokens=getattr(meta, "prompt_tokens_details", None) and getattr(meta.prompt_tokens_details, "cached_tokens", 0),
        output_tokens=getattr(meta, "completion_tokens", 0) or 0,
        latency=timer.latency(),
        time_to_first_token=timer.time_to_first_token,
    )


def _api_error(exc: APIError) -> ProviderError:
    """Maps an OpenAI API error to a retryable or permanent error."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = f"OpenAI-compatible API returned {code}: {getattr(exc, 'message', exc)}"
    if code == 429 or (code and code >= 500) or isinstance(exc, RateLimitError):
        retry_after = None
        headers = getattr(exc, "response", None) and getattr(exc.response, "headers", None)
        if headers and "retry-after" in headers:
            try:
                retry_after = float(headers["retry-after"])
            except (ValueError, TypeError):
                pass
        return RetryableError(message, retry_after=retry_after)
    return ProviderError(message)
