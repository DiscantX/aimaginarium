"""Tests for the Gemini provider, using a stand-in for the SDK client."""

import asyncio

import httpx
import pytest
from pydantic import BaseModel

pytest.importorskip("google.genai")
from google.genai import errors, types  # noqa: E402

from aimaginarium.llm import Capabilities, Chunk, Message, ProviderError, Request, Response, RetryableError  # noqa: E402
from aimaginarium.llm.providers.gemini import GeminiProvider  # noqa: E402


class Reply(BaseModel):
    narration: str


def chunk(text=None, usage=None, finish=None):
    parts = [types.Part(text=text)] if text else []
    candidate = types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)
    return types.GenerateContentResponse(candidates=[candidate], usage_metadata=usage)


class FakeModels:
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error, self.calls = chunks, error, []

    async def generate_content_stream(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error

        async def gen():
            for item in self.chunks:
                yield item
        return gen()


class FakeClient:
    def __init__(self, **kwargs):
        self.models = FakeModels(**kwargs)
        self.aio = type("Aio", (), {"models": self.models})()


def provider(**kwargs):
    client = FakeClient(**kwargs)
    return GeminiProvider("gemini-test", client=client), client.models


def run_stream(gemini, request):
    async def go():
        return [event async for event in gemini.stream(request)]
    return asyncio.run(go())


USAGE = types.GenerateContentResponseUsageMetadata(
    prompt_token_count=100, cached_content_token_count=80, candidates_token_count=10, thoughts_token_count=5
)


def test_streams_chunks_then_response_with_usage():
    gemini, _ = provider(chunks=[chunk("Hel"), chunk("lo", usage=USAGE)])
    events = run_stream(gemini, Request())
    assert [e.text for e in events[:-1]] == ["Hel", "lo"] and all(isinstance(e, Chunk) for e in events[:-1])
    final = events[-1]
    assert isinstance(final, Response) and final.text == "Hello" and final.model == "gemini-test"
    assert (final.usage.prompt_tokens, final.usage.cached_tokens, final.usage.output_tokens) == (100, 80, 15)
    assert final.usage.time_to_first_token is not None
    assert final.usage.time_to_first_token >= 0


def test_request_mapping():
    gemini, models = provider(chunks=[chunk("x")])
    request = Request(system="rules", messages=(Message("user", "hi"), Message("assistant", "yo")),
                      schema=Reply, temperature=0.4, model="other")
    run_stream(gemini, request)
    call = models.calls[0]
    assert call["model"] == "other"
    assert [c.role for c in call["contents"]] == ["user", "model"]
    config = call["config"]
    assert config.system_instruction == "rules" and config.temperature == 0.4
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == Reply.model_json_schema()
    assert config.automatic_function_calling.disable is True


def test_json_mode_and_extra_config():
    client = FakeClient(chunks=[chunk("x")])
    gemini = GeminiProvider("m", client=client, config={"thinking_config": {"thinking_budget": 0}},
                            capabilities={"m": Capabilities(json_mode=True)})
    run_stream(gemini, Request(schema=Reply))
    config = client.models.calls[0]["config"]
    assert config.response_mime_type == "application/json" and config.response_json_schema is None
    assert config.thinking_config.thinking_budget == 0


@pytest.mark.parametrize("error_class,code,expected", [
    (errors.ServerError, 503, RetryableError), (errors.ClientError, 429, RetryableError),
    (errors.ClientError, 400, ProviderError),
])
def test_api_errors(error_class, code, expected):
    gemini, _ = provider(error=error_class(code, {"error": {"code": code, "message": "no"}}))
    with pytest.raises(expected) as info:
        run_stream(gemini, Request())
    assert isinstance(info.value, RetryableError) == (expected is RetryableError)


def test_connection_failure_is_retryable():
    gemini, _ = provider(error=httpx.ConnectError("refused"))
    with pytest.raises(RetryableError):
        run_stream(gemini, Request())


def test_no_text_is_an_error():
    gemini, _ = provider(chunks=[chunk(None, finish=types.FinishReason.SAFETY)])
    with pytest.raises(ProviderError, match="SAFETY"):
        run_stream(gemini, Request())


def test_server_suggested_wait_is_passed_on():
    info = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"}
    gemini, _ = provider(error=errors.ClientError(429, {"error": {"code": 429, "message": "slow down", "details": [info]}}))
    with pytest.raises(RetryableError) as caught:
        run_stream(gemini, Request())
    assert caught.value.retry_after == 34.0


def test_no_suggested_wait_when_the_server_gives_none():
    gemini, _ = provider(error=errors.ServerError(503, {"error": {"code": 503, "message": "overloaded"}}))
    with pytest.raises(RetryableError) as caught:
        run_stream(gemini, Request())
    assert caught.value.retry_after is None
