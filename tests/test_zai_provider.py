"""Tests for the Z.AI / OpenAI provider, using a stand-in for the OpenAI client."""

import asyncio
import pytest
from pydantic import BaseModel

pytest.importorskip("openai")
from openai import APIError, RateLimitError  # noqa: E402

from aimaginarium.llm import Capabilities, Chunk, Message, ProviderError, Request, Response, RetryableError  # noqa: E402
from aimaginarium.llm.providers.zai import ZAIProvider  # noqa: E402


class Reply(BaseModel):
    narration: str


class Delta:
    def __init__(self, content=None, reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content


class Choice:
    def __init__(self, delta=None):
        self.delta = delta


class ChunkObj:
    def __init__(self, content=None, reasoning_content=None, usage=None):
        self.choices = [Choice(Delta(content=content, reasoning_content=reasoning_content))]
        self.usage = usage


class UsageObj:
    def __init__(self, prompt_tokens=10, completion_tokens=5):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeCompletions:
    def __init__(self, chunks=(), error=None):
        self.chunks = chunks
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error

        def gen():
            for item in self.chunks:
                yield item
        return gen()


class FakeChat:
    def __init__(self, **kwargs):
        self.completions = FakeCompletions(**kwargs)


class FakeClient:
    def __init__(self, **kwargs):
        self.chat = FakeChat(**kwargs)


def provider(**kwargs):
    client = FakeClient(**kwargs)
    return ZAIProvider(client=client), client.chat.completions


def run_stream(zai, request):
    async def go():
        return [event async for event in zai.stream(request)]
    return asyncio.run(go())


def test_default_model_and_capabilities():
    zai = ZAIProvider(api_key="test")
    assert zai.default_model == "glm-4.7-flash"
    caps = zai.capabilities()
    assert caps.schema_enforcement is True


def test_streams_chunks_then_response_with_usage():
    usage = UsageObj(prompt_tokens=50, completion_tokens=20)
    zai, _ = provider(chunks=[ChunkObj(content="Hel"), ChunkObj(content="lo", usage=usage)])
    events = run_stream(zai, Request())
    assert [e.text for e in events[:-1]] == ["Hel", "lo"]
    final = events[-1]
    assert isinstance(final, Response)
    assert final.text == "Hello"
    assert final.model == "glm-4.7-flash"
    assert final.usage.prompt_tokens == 50
    assert final.usage.output_tokens == 20


def test_request_mapping():
    zai, completions = provider(chunks=[ChunkObj(content="x")])
    request = Request(
        system="be kind",
        messages=(Message("user", "hello"), Message("assistant", "hi")),
        schema=Reply,
        temperature=0.7,
        model="glm-4.7-flash",
    )
    run_stream(zai, request)
    call = completions.calls[0]
    assert call["model"] == "glm-4.7-flash"
    assert call["temperature"] == 0.7
    assert call["stream"] is True
    assert call["messages"][0] == {"role": "system", "content": "be kind"}
    assert call["messages"][1] == {"role": "user", "content": "hello"}
    assert call["messages"][2] == {"role": "assistant", "content": "hi"}
    assert call["response_format"]["type"] == "json_schema"


def test_api_errors():
    err = APIError(message="rate limited", request=None, body=None)
    err.status_code = 429
    zai, _ = provider(error=err)
    with pytest.raises(RetryableError):
        run_stream(zai, Request())
