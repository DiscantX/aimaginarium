"""Tests for retry with backoff."""

import asyncio

import pytest

from aimaginarium.llm import (
    Capabilities, Chunk, LLMProvider, ProviderError, ProviderUnavailableError, Request, RetryableError,
    RetryingProvider, RetryPolicy,
)
from aimaginarium.llm.providers.fake import FakeProvider

BUSY = RetryableError("503 busy")
STEADY = RetryPolicy(jitter=0)


class Recorder:
    """Stands in for ``asyncio.sleep`` and records the waits."""

    def __init__(self):
        self.waits = []

    async def __call__(self, seconds):
        self.waits.append(seconds)


class FailsAfterText(LLMProvider):
    def capabilities(self, model=None):
        return Capabilities()

    async def stream(self, request):
        yield Chunk("partial")
        raise BUSY


def wrap(replies, policy=STEADY, notices=None):
    sleep = Recorder()
    fake = FakeProvider(replies)
    notify = notices.append if notices is not None else None
    return RetryingProvider(fake, policy, on_retry=notify, sleep=sleep), fake, sleep


def generate(provider):
    return asyncio.run(provider.generate(Request()))


def test_retries_with_doubling_waits_then_succeeds():
    notices = []
    provider, fake, sleep = wrap([BUSY, BUSY, "ok"], notices=notices)
    assert generate(provider).text == "ok"
    assert sleep.waits == [1.0, 2.0] and len(fake.requests) == 3
    assert [(n.attempt, n.delay) for n in notices] == [(1, 1.0), (2, 2.0)]


def test_gives_up_after_the_attempt_limit():
    provider, _, sleep = wrap([BUSY] * 3, RetryPolicy(attempts=3, jitter=0))
    with pytest.raises(ProviderUnavailableError) as info:
        generate(provider)
    assert (info.value.attempts, info.value.waited) == (3, 3.0) and sleep.waits == [1.0, 2.0]


def test_gives_up_before_exceeding_the_total_wait():
    provider, _, sleep = wrap([BUSY] * 6, RetryPolicy(max_total_wait=3, jitter=0))
    with pytest.raises(ProviderUnavailableError) as info:
        generate(provider)
    assert sleep.waits == [1.0, 2.0] and info.value.waited == 3.0


def test_waits_as_long_as_the_server_asks():
    provider, _, sleep = wrap([RetryableError("429", retry_after=7), "ok"])
    assert generate(provider).text == "ok" and sleep.waits == [7]


def test_gives_up_at_once_when_the_server_asks_for_too_long():
    provider, fake, sleep = wrap([RetryableError("429", retry_after=3600), "never used"])
    with pytest.raises(ProviderUnavailableError):
        generate(provider)
    assert sleep.waits == [] and len(fake.requests) == 1


def test_other_errors_are_not_retried():
    provider, fake, sleep = wrap([ProviderError("bad key"), "ok"])
    with pytest.raises(ProviderError):
        generate(provider)
    assert sleep.waits == [] and len(fake.requests) == 1


def test_failure_after_text_was_streamed_is_not_retried():
    sleep = Recorder()
    provider = RetryingProvider(FailsAfterText(), STEADY, sleep=sleep)
    with pytest.raises(RetryableError) as info:
        generate(provider)
    assert not isinstance(info.value, ProviderUnavailableError) and sleep.waits == []


def test_jitter_stays_within_bounds_and_waits_are_capped():
    policy = RetryPolicy(base_delay=1, max_delay=5, jitter=0.25)
    for attempt, ceiling in [(1, 1.25), (3, 5.0), (10, 6.25)]:
        assert 0.75 <= policy.delay(attempt, 0, BUSY) <= ceiling


def test_capabilities_pass_through():
    provider, _, _ = wrap([])
    assert provider.capabilities() == Capabilities(schema_enforcement=True)
