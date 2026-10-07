"""Tests for per-task fallback chains and the cool-down."""

import asyncio

import pytest
from pydantic import BaseModel

from aimaginarium.llm import (
    Capabilities, ConfigError, Message, ProviderFactory, ProviderUnavailableError, Request, StructuredOutputError,
)
from aimaginarium.llm.providers.fake import FakeProvider

DOWN = ProviderUnavailableError("busy", attempts=6, waited=45)


class Reply(BaseModel):
    text: str


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def make(providers, tasks, notices=None, clock=None, cooldown=60):
    """Builds a factory whose providers replay the scripted ``replies`` in their specs."""
    config = {
        "providers": {n: {"kind": "fake", "model": m, "replies": r} for n, (m, r) in providers.items()},
        "tasks": tasks,
        "fallback": {"cooldown": cooldown},
    }
    built = {}

    def builder(spec, env):
        built[spec["model"]] = FakeProvider(list(spec["replies"]), capabilities=Capabilities(schema_enforcement=True))
        return built[spec["model"]]

    factory = ProviderFactory(config, env={}, builders={"fake": builder}, on_fallback=(notices.append if notices is not None else None),
                              clock=clock or Clock())
    return factory, built


def run(coro):
    return asyncio.run(coro)


REQUEST = Request(messages=(Message("user", "hi"),))


def test_primary_is_used_when_available():
    f, built = make({"a": ("big", ["one"]), "b": ("small", ["two"])}, {"default": {"provider": "a", "fallback": ["b"]}})
    assert run(f.route("x").generate(REQUEST)).text == "one"
    assert built["small"].requests == []


def test_falls_back_in_order_and_reports_it():
    notices = []
    f, built = make(
        {"a": ("big", [DOWN]), "b": ("mid", [DOWN]), "c": ("small", ["third"])},
        {"default": {"provider": "a", "fallback": ["b", "c"]}}, notices)
    response = run(f.route("narrate").generate(REQUEST))
    assert (response.text, response.model) == ("third", "small")
    assert [(n.task, n.failed, n.next) for n in notices] == [("narrate", "a:big", "b:mid"), ("narrate", "b:mid", "c:small")]


def test_fallback_entry_can_name_a_model_containing_colons():
    f, built = make({"a": ("big", [DOWN]), "b": ("dflt", ["x"])}, {"default": {"provider": "a", "fallback": ["b:phi4:mini"]}})
    assert run(f.route("x").generate(REQUEST)).model == "phi4:mini"


def test_every_candidate_down_raises_unavailable():
    f, _ = make({"a": ("big", [DOWN]), "b": ("small", [DOWN])}, {"default": {"provider": "a", "fallback": ["b"]}})
    with pytest.raises(ProviderUnavailableError, match="every provider"):
        run(f.route("x").generate(REQUEST))


def test_cooldown_skips_a_failed_candidate_until_it_expires():
    clock = Clock()
    f, built = make(
        {"a": ("big", [DOWN, "back"]), "b": ("small", ["s1", "s2"])},
        {"default": {"provider": "a", "fallback": ["b"]}}, clock=clock, cooldown=60)
    route = f.route("x")
    assert run(route.generate(REQUEST)).text == "s1"
    assert run(route.generate(REQUEST)).text == "s2"  # a is skipped: it was not asked again
    assert len(built["big"].requests) == 1
    clock.now = 61
    assert run(route.generate(REQUEST)).model == "big"  # probed again after the window


def test_all_cooling_down_still_tries_everything():
    clock = Clock()
    f, _ = make({"a": ("big", [DOWN, "ok"])}, {"default": {"provider": "a"}}, clock=clock)
    route = f.route("x")
    with pytest.raises(ProviderUnavailableError):
        run(route.generate(REQUEST))
    assert run(route.generate(REQUEST)).text == "ok"


def test_cooldown_is_shared_between_tasks():
    f, built = make(
        {"a": ("big", [DOWN]), "b": ("small", ["1", "2"])},
        {"default": {"provider": "a", "fallback": ["b"]}, "other": {"provider": "a", "fallback": ["b"]}})
    run(f.route("x").generate(REQUEST))
    run(f.route("other").generate(REQUEST))
    assert len(built["big"].requests) == 1


def test_failure_after_text_has_streamed_is_not_a_fallback():
    class Breaks(FakeProvider):
        async def stream(self, request):
            from aimaginarium.llm import Chunk
            yield Chunk("part")
            raise DOWN

    config = {"providers": {"a": {"kind": "x", "model": "m"}, "b": {"kind": "fake", "model": "s"}},
              "tasks": {"default": {"provider": "a", "fallback": ["b"]}}}
    f = ProviderFactory(config, env={}, builders={"x": lambda s, e: Breaks([]), "fake": lambda s, e: FakeProvider(["no"])})

    async def go():
        return [e async for e in f.route("t").stream(REQUEST)]

    with pytest.raises(ProviderUnavailableError):
        run(go())


def test_structured_call_checks_capabilities_per_candidate():
    config = {"providers": {"a": {"kind": "fake", "model": "big"}, "b": {"kind": "fake", "model": "small"}},
              "tasks": {"default": {"provider": "a", "fallback": ["b"]}}}
    built = {}

    def builder(spec, env):
        enforced = spec["model"] == "big"
        replies = [DOWN] if enforced else ['{"text": "hello"}']
        built[spec["model"]] = FakeProvider(replies, capabilities=Capabilities(schema_enforcement=enforced))
        return built[spec["model"]]

    f = ProviderFactory(config, env={}, builders={"fake": builder})
    value, response = run(f.route("x").call(REQUEST, Reply))
    assert value == Reply(text="hello") and response.model == "small"
    assert "JSON schema" in built["small"].requests[0].system  # schema described for the candidate that cannot enforce it


def test_structured_failure_falls_back_without_cooling_down():
    f, built = make(
        {"a": ("big", ["nope", "nope", "nope", '{"text": "again"}']), "b": ("small", ['{"text": "ok"}', '{"text": "ok"}'])},
        {"default": {"provider": "a", "fallback": ["b"]}})
    route = f.route("x")
    assert run(route.call(REQUEST, Reply))[1].model == "small"
    assert run(route.call(REQUEST, Reply))[1].model == "big"  # not skipped: bad output is not an outage


def test_structured_call_raises_when_the_last_candidate_gives_nothing_valid():
    f, _ = make({"a": ("big", ["x", "x", "x"])}, {"default": {"provider": "a"}})
    with pytest.raises(StructuredOutputError):
        run(f.route("x").call(REQUEST, Reply))


def test_a_fallback_naming_an_undefined_provider_is_a_config_error():
    f, _ = make({"a": ("big", [])}, {"default": {"provider": "a", "fallback": ["ghost"]}})
    with pytest.raises(ConfigError, match="not defined"):
        f.route("x")
