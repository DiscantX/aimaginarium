"""Tests for provider construction and per-task routing."""

import pytest

from aimaginarium.llm import Capabilities, ConfigError, ProviderFactory, Request
from aimaginarium.llm.providers.fake import FakeProvider

CONFIG = {
    "providers": {
        "main": {"kind": "fake", "model": "big"},
        "small": {"kind": "fake", "model": "tiny"},
    },
    "tasks": {
        "default": {"provider": "main"},
        "check": {"provider": "small"},
        "narrate": {"provider": "main", "model": "bigger"},
    },
}
BUILT = []


def build_fake(spec, env):
    BUILT.append(spec["model"])
    return FakeProvider([])


def factory(config=CONFIG, env=None):
    BUILT.clear()
    return ProviderFactory(config, env=env or {}, builders={"fake": build_fake})


def test_routes_each_task_to_its_provider_and_model():
    f = factory()
    assert f.route("check").model == "tiny"
    assert f.route("narrate").model == "bigger"
    assert f.route("anything-else").model == "big"


def test_provider_is_built_once_and_shared():
    f = factory()
    assert f.route("narrate").provider is f.route("default").provider
    assert BUILT.count("big") == 1


def test_with_model_addresses_the_request():
    assert factory().route("check").with_model(Request(system="s")).model == "tiny"


@pytest.mark.parametrize("config,message", [
    ({"providers": {}, "tasks": {}}, "no default"),
    ({"providers": {}, "tasks": {"default": {"provider": "x"}}}, "not defined"),
    ({"providers": {"x": {"kind": "nope", "model": "m"}}, "tasks": {"default": {"provider": "x"}}}, "unknown kind"),
])
def test_configuration_errors(config, message):
    with pytest.raises(ConfigError, match=message):
        factory(config).route("check")


def test_ollama_provider_gets_its_settings():
    config = {"providers": {"local": {"kind": "ollama", "model": "phi4-mini", "base_url": "http://box:11434",
                                      "options": {"num_thread": 2},
                                      "capabilities": {"phi4-mini": {"json_mode": True}}}},
              "tasks": {"default": {"provider": "local"}}}
    provider = factory(config).route("x").provider.inner
    assert provider.base_url == "http://box:11434" and provider.default_model == "phi4-mini"
    assert provider.capabilities() == Capabilities(json_mode=True)


def test_gemini_requires_its_key():
    pytest.importorskip("google.genai")
    config = {"providers": {"g": {"kind": "gemini", "model": "m"}}, "tasks": {"default": {"provider": "g"}}}
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        factory(config).route("x")
    assert factory(config, env={"GEMINI_API_KEY": "k"}).route("x").model == "m"
    renamed = {"providers": {"g": {"kind": "gemini", "model": "m", "api_key_env": "MY_KEY"}},
               "tasks": {"default": {"provider": "g"}}}
    assert factory(renamed, env={"MY_KEY": "k"}).route("x").model == "m"


def test_providers_are_wrapped_with_the_configured_retry_policy():
    config = {**CONFIG, "retry": {"attempts": 3, "max_total_wait": 10},
              "providers": {**CONFIG["providers"], "small": {**CONFIG["providers"]["small"], "retry": {"attempts": 2}}}}
    f = factory(config)
    assert (f.route("narrate").provider.policy.attempts, f.route("narrate").provider.policy.max_total_wait) == (3, 10)
    assert f.route("check").provider.policy.attempts == 2
