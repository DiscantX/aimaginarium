"""Tests for the startup shared by every client."""

import argparse

import pytest

from aimaginarium.llm import ConfigError
from aimaginarium.ui.bootstrap import Runtime, add_common_arguments, open_world


def parse(*argv):
    parser = argparse.ArgumentParser()
    add_common_arguments(parser)
    return parser.parse_args(argv)


def test_common_arguments_have_defaults():
    args = parse()
    assert args.world == "worlds/demo.sqlite"
    assert not args.dev and args.trace is None and args.config is None


def test_open_world_creates_the_demo_world_then_reopens_it(tmp_path):
    path = tmp_path / "sub" / "w.sqlite"
    store, player_id, begun = open_world(path)
    store.close()
    assert not begun
    store, again, begun = open_world(path)
    store.close()
    assert again == player_id


def test_runtime_reports_a_missing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AIMAGINARIUM_CONFIG", raising=False)
    with pytest.raises(ConfigError):
        Runtime.open(parse("--world", str(tmp_path / "w.sqlite")))
    assert not (tmp_path / "w.sqlite").exists()
