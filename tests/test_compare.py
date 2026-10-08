"""Tests for the blind model comparison."""

import asyncio
import json

from aimaginarium.compare import SCENARIOS, compare, summary, write_report
from aimaginarium.llm import Capabilities, ProviderFactory, ProviderUnavailableError
from aimaginarium.llm.providers.fake import FakeProvider


def reply(n):
    return json.dumps({"narration": [f"para {i}" for i in range(n)], "changes": []})


def factory(scripts):
    config = {"providers": {name: {"kind": "fake", "model": name} for name in scripts},
              "tasks": {"default": {"provider": next(iter(scripts))}}}
    return ProviderFactory(config, env={}, builders={
        "fake": lambda spec, env: FakeProvider(list(scripts[spec["model"]]), capabilities=Capabilities(schema_enforcement=True))})


def test_every_model_gets_every_scenario_and_is_scored():
    results = asyncio.run(compare(factory({
        "good": [reply(7), reply(1), reply(1)],
        "bad": ["not json", reply(9), ProviderUnavailableError("busy", attempts=1, waited=0)],
    }), ["good", "bad"]))
    assert [(r.scenario, r.model) for r in results] == [(s, m) for s in SCENARIOS for m in ("good:good", "bad:bad")]
    by = {(r.scenario, r.model): r for r in results}
    assert by["opening", "good:good"].valid and by["opening", "good:good"].paragraphs == 7
    assert "unreadable" in by["opening", "bad:bad"].error
    assert not by["action", "bad:bad"].valid and by["action", "bad:bad"].paragraphs == 9 and "schema" in by["action", "bad:bad"].error
    assert "Unavailable" in by["check_outcome", "bad:bad"].error


def test_blind_file_hides_the_models_and_the_key_maps_them_back(tmp_path):
    results = asyncio.run(compare(factory({"a": [reply(7)], "b": [reply(7)]}), ["a", "b"], ["opening"]))
    write_report(results, tmp_path, seed=1)
    blind = (tmp_path / "blind.md").read_text()
    assert "a:a" not in blind and "b:b" not in blind and "### A" in blind and "### B" in blind
    key = json.loads((tmp_path / "key.json").read_text())
    assert sorted(key.values()) == ["a:a", "b:b"] and set(key) == {"opening/1/A", "opening/1/B"}
    assert len(json.loads((tmp_path / "metrics.json").read_text())) == 2


def test_summary_names_the_models():
    results = asyncio.run(compare(factory({"a": [reply(7)]}), ["a"], ["opening"]))
    assert "a:a" in summary(results) and "1/1" in summary(results)
