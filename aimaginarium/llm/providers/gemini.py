"""Gemini provider, using Google's official ``google-genai`` SDK.

Install the optional dependency with ``pip install "aimaginarium[gemini]"``.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Optional

import httpx

try:
    from google import genai
    from google.genai import errors, types
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise ImportError('The Gemini provider needs the SDK: pip install "aimaginarium[gemini]"') from exc

from ..base import (
    Capabilities, Chunk, LLMProvider, ProviderError, Request, Response, RetryableError, StreamEvent, Usage, ResponseTimer,
)

DEFAULT_CAPABILITIES = Capabilities(schema_enforcement=True, json_mode=True, reports_cache=True, tool_calling=True)
_ROLES = {"user": "user", "assistant": "model"}


class GeminiProvider(LLMProvider):
    """Runs requests against the Gemini API.

    Attributes:
        default_model: Model used when a request names none.
    """

    def __init__(
        self,
        default_model: str,
        api_key: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        capabilities: Optional[dict[str, Capabilities]] = None,
        client: Optional[Any] = None,
    ):
        """Initialises the provider.

        Args:
            default_model: Model used when a request names none.
            api_key: API key; if omitted the SDK reads it from the environment.
            config: Extra ``GenerateContentConfig`` fields sent with every request,
                such as ``{"thinking_config": {"thinking_budget": 0}}``.
            capabilities: Per-model overrides of :data:`DEFAULT_CAPABILITIES`.
            client: A ready ``genai.Client`` (or a test double); one is created if omitted.
        """
        self.default_model = default_model
        self._config = dict(config or {})
        self._capabilities = capabilities or {}
        self._client = client or genai.Client(api_key=api_key)

    def capabilities(self, model: Optional[str] = None) -> Capabilities:
        """Returns the override for ``model`` if given, else the defaults."""
        return self._capabilities.get(model or self.default_model, DEFAULT_CAPABILITIES)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Streams a generation.

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
        finish = None
        try:
            chunks = await self._client.aio.models.generate_content_stream(
                model=model, contents=_contents(request), config=self._build_config(request, model)
            )
            async for chunk in chunks:
                usage = chunk.usage_metadata or usage
                if chunk.candidates and chunk.candidates[0].finish_reason:
                    finish = chunk.candidates[0].finish_reason
                if chunk.text:
                    timer.record_chunk()
                    text.append(chunk.text)
                    yield Chunk(chunk.text)
        except errors.APIError as exc:
            raise _api_error(exc) from exc
        except httpx.TransportError as exc:
            raise RetryableError(f"cannot reach Gemini: {exc}") from exc
        if not text:
            raise ProviderError(f"Gemini returned no text (finish reason: {finish})")
        yield Response("".join(text), model, _usage(usage, timer))

    def _build_config(self, request: Request, model: str) -> "types.GenerateContentConfig":
        """Builds the generation config for a request."""
        # The engine, not the SDK, executes tool calls, so the SDK's automatic loop stays off.
        fields = {"automatic_function_calling": {"disable": True}, **self._config}
        if request.system:
            fields["system_instruction"] = request.system
        if request.temperature is not None:
            fields["temperature"] = request.temperature
        caps = self.capabilities(model)
        if request.schema is not None and caps.schema_enforcement:
            fields["response_mime_type"] = "application/json"
            fields["response_json_schema"] = request.schema.model_json_schema()
        elif request.schema is not None and caps.json_mode:
            fields["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(**fields)


def _contents(request: Request) -> list:
    """Converts the conversation to Gemini's role and parts format."""
    return [types.Content(role=_ROLES[m.role], parts=[types.Part(text=m.content)]) for m in request.messages]


def _usage(meta: Any, timer: ResponseTimer) -> Usage:
    """Builds :class:`Usage`; thinking tokens count as output because they take time and money."""
    if meta is None:
        return Usage(latency=timer.latency(), time_to_first_token=timer.time_to_first_token)
    return Usage(
        prompt_tokens=meta.prompt_token_count or 0,
        cached_tokens=meta.cached_content_token_count or 0,
        output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
        latency=timer.latency(),
        time_to_first_token=timer.time_to_first_token,
    )


def _api_error(exc: "errors.APIError") -> ProviderError:
    """Maps an SDK error to a retryable or permanent error."""
    message = f"Gemini returned {exc.code}: {getattr(exc, 'message', exc)}"
    if exc.code == 429 or (exc.code or 0) >= 500:
        return RetryableError(message, retry_after=_retry_after(exc))
    return ProviderError(message)


def _retry_after(exc: "errors.APIError") -> Optional[float]:
    """Reads the wait the server suggested (``RetryInfo.retryDelay``, such as ``"34s"``), if any."""
    details = exc.details.get("error", {}).get("details", []) if isinstance(exc.details, dict) else []
    for item in details:
        if str(item.get("@type", "")).endswith("RetryInfo"):
            try:
                return float(str(item["retryDelay"]).rstrip("s"))
            except (KeyError, ValueError):
                return None
    return None
