"""Tests for the LLM gateway: base interface, retry and structured output."""

import asyncio

import pytest
from pydantic import BaseModel

from aimaginarium.llm import (
    Capabilities, Chunk, Message, ProviderError, Request, Response, RetryableError,
    StructuredCaller, StructuredOutputError, retry,
)
from aimaginarium.llm.providers.fake import FakeProvider


class Reply(BaseModel):
    narration: str
    hp: int = 0


def run(coro):
    return asyncio.run(coro)


def collect(provider, request):
    async def go():
        return [event async for event in provider.stream(request)]
    return run(go())


def test_stream_yields_chunks_then_one_response():
    events = collect(FakeProvider(["hello world!"], chunk_size=5), Request())
    assert [e.text for e in events[:-1]] == ["hello", " worl", "d!"]
    assert all(isinstance(e, Chunk) for e in events[:-1])
    assert isinstance(events[-1], Response) and events[-1].text == "hello world!"


def test_generate_returns_final_response_and_records_request():
    provider = FakeProvider(["ok"])
    request = Request(system="s", messages=(Message("user", "hi"),))
    assert run(provider.generate(request)).text == "ok"
    assert provider.requests == [request]


def test_scripted_exception_is_raised():
    with pytest.raises(ProviderError):
        run(FakeProvider([ProviderError("boom")]).generate(Request()))


def test_retry_succeeds_after_retryable_failures():
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("busy")
        return "done"

    assert run(retry(flaky, attempts=3, backoff=0)) == "done"
    assert len(calls) == 3


def test_retry_gives_up_after_attempts():
    async def always():
        raise RetryableError("busy")

    with pytest.raises(RetryableError):
        run(retry(always, attempts=2, backoff=0))


def test_retry_does_not_repeat_other_errors():
    calls = []

    async def broken():
        calls.append(1)
        raise ProviderError("bad key")

    with pytest.raises(ProviderError):
        run(retry(broken, attempts=3, backoff=0))
    assert len(calls) == 1


def test_structured_returns_valid_reply():
    provider = FakeProvider(['{"narration": "You enter.", "hp": -2}'])
    reply, response = run(StructuredCaller(provider).call(Request(), Reply))
    assert reply == Reply(narration="You enter.", hp=-2)
    assert response.text.startswith("{")
    assert provider.requests[0].schema is Reply


def test_structured_accepts_fenced_json():
    provider = FakeProvider(['```json\n{"narration": "ok"}\n```'])
    reply, _ = run(StructuredCaller(provider).call(Request(), Reply))
    assert reply.narration == "ok"


def test_structured_feeds_errors_back_and_retries():
    provider = FakeProvider(['{"hp": "lots"}', '{"narration": "fixed"}'])
    reply, _ = run(StructuredCaller(provider).call(Request(messages=(Message("user", "go"),)), Reply))
    assert reply.narration == "fixed"
    retry_messages = provider.requests[1].messages
    assert [m.role for m in retry_messages] == ["user", "assistant", "user"]
    assert "narration" in retry_messages[-1].content


def test_structured_raises_when_attempts_run_out():
    provider = FakeProvider(["not json"] * 3)
    with pytest.raises(StructuredOutputError):
        run(StructuredCaller(provider, max_attempts=3).call(Request(), Reply))
    assert len(provider.requests) == 3


def test_schema_described_in_prompt_only_when_not_enforced():
    enforced = FakeProvider(['{"narration": "a"}'], Capabilities(schema_enforcement=True))
    run(StructuredCaller(enforced).call(Request(system="base"), Reply))
    assert enforced.requests[0].system == "base"

    plain = FakeProvider(['{"narration": "a"}'], Capabilities())
    run(StructuredCaller(plain).call(Request(system="base"), Reply))
    assert plain.requests[0].system.startswith("base") and "narration" in plain.requests[0].system
