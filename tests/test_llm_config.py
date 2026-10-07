"""Tests for reading the LLM configuration from TOML."""

import pytest

from aimaginarium.llm import ConfigError, Capabilities, factory_from_file, find_config, load_config

TOML = """
[providers.local]
kind = "ollama"
model = "phi4-mini"
options = { num_thread = 2 }

[providers.local.capabilities.phi4-mini]
json_mode = true

[tasks.default]
provider = "local"

[tasks.check]
provider = "local"
model = "tiny"
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "a.toml"
    path.write_text(TOML)
    return path


def test_load_config_gives_the_factory_mapping(config_file):
    config = load_config(config_file)
    assert config["providers"]["local"]["options"] == {"num_thread": 2}
    assert config["tasks"]["check"] == {"provider": "local", "model": "tiny"}


def test_factory_from_file_routes_tasks(config_file):
    factory = factory_from_file(config_file, env={})
    assert factory.route("check").model == "tiny"
    assert factory.route("other").model == "phi4-mini"
    assert factory.route("other").provider.capabilities() == Capabilities(json_mode=True)


def test_path_falls_back_to_environment_then_default_name(config_file, monkeypatch, tmp_path):
    monkeypatch.setenv("AIMAGINARIUM_CONFIG", str(config_file))
    assert find_config() == config_file
    monkeypatch.delenv("AIMAGINARIUM_CONFIG")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="not found"):
        find_config()
    (tmp_path / "aimaginarium.toml").write_text(TOML)
    assert find_config().name == "aimaginarium.toml"


def test_invalid_toml_is_a_config_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("providers = [")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(bad)


def test_example_file_is_valid_and_complete():
    config = load_config("aimaginarium.example.toml")
    assert set(config["tasks"]) >= {"default"}
    assert all(t["provider"] in config["providers"] for t in config["tasks"].values())
