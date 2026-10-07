"""Tests for the Ollama provider, using a mock HTTP transport."""

import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel

from aimaginarium.llm import Capabilities, Chunk, Message, ProviderError, Request, Response, RetryableError
from aimaginarium.llm.providers.ollama import OllamaProvider


class Reply(BaseModel):
    narration: str


def ndjson(*parts: dict) -> bytes:
    return "".join(json.dumps(p) + "\n" for p in parts).encode()


def provider(handler, **kwargs) -> OllamaProvider:
    client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    return OllamaProvider("phi4-mini", client=client, **kwargs)


def run_stream(ollama, request):
    async def go():
        return [event async for event in ollama.stream(request)]
    return asyncio.run(go())


FINAL = {"model": "phi4-mini", "message": {"content": ""}, "done": True,
         "prompt_eval_count": 120, "prompt_eval_cached_count": 100, "eval_count": 9}


def test_streams_chunks_then_response_with_usage():
    body = ndjson({"message": {"content": "Hel"}, "done": False}, {"message": {"content": "lo"}, "done": False}, FINAL)
    events = run_stream(provider(lambda r: httpx.Response(200, content=body)), Request())
    assert [e.text for e in events[:-1]] == ["Hel", "lo"]
    final = events[-1]
    assert isinstance(final, Response) and final.text == "Hello"
    assert (final.usage.prompt_tokens, final.usage.cached_tokens, final.usage.output_tokens) == (120, 100, 9)


def test_cached_tokens_none_when_server_omits_the_field():
    body = ndjson({k: v for k, v in FINAL.items() if k != "prompt_eval_cached_count"})
    final = run_stream(provider(lambda r: httpx.Response(200, content=body)), Request())[-1]
    assert final.usage.cached_tokens is None


def test_request_body():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=ndjson(FINAL))

    request = Request(system="rules", messages=(Message("user", "hi"),), schema=Reply, temperature=0.5)
    run_stream(provider(handler, options={"num_ctx": 4096, "num_thread": 2}), request)
    assert seen["model"] == "phi4-mini" and seen["stream"] is True
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]
    assert seen["format"] == Reply.model_json_schema()
    assert seen["options"] == {"num_ctx": 4096, "num_thread": 2, "temperature": 0.5}


def test_json_mode_when_schema_not_supported():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=ndjson(FINAL))

    caps = {"phi4-mini": Capabilities(json_mode=True)}
    run_stream(provider(handler, capabilities=caps), Request(schema=Reply))
    assert seen["format"] == "json"


@pytest.mark.parametrize("status,error", [(500, RetryableError), (429, RetryableError), (404, ProviderError)])
def test_http_errors(status, error):
    with pytest.raises(error) as info:
        run_stream(provider(lambda r: httpx.Response(status, content=b"nope")), Request())
    assert (status == 404) == (not isinstance(info.value, RetryableError))


def test_connection_failure_is_retryable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(RetryableError):
        run_stream(provider(handler), Request())


def test_error_line_and_truncated_stream():
    with pytest.raises(ProviderError):
        run_stream(provider(lambda r: httpx.Response(200, content=ndjson({"error": "model not found"}))), Request())
    with pytest.raises(ProviderError):
        run_stream(provider(lambda r: httpx.Response(200, content=ndjson({"message": {"content": "x"}}))), Request())
