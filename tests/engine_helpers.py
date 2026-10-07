"""Shared helpers for the engine and client tests."""

import json

from aimaginarium.engine import Game, PLAYER_ID, D20Rules
from aimaginarium.llm import Capabilities, ProviderFactory
from aimaginarium.llm.providers.fake import FakeProvider
from aimaginarium.prompts import PromptBuilder


class FixedDice:
    """Stands in for ``random.Random``: always rolls the same number."""

    def __init__(self, die):
        self.die = die

    def randint(self, low, high):
        return self.die


def reply(narration, changes=(), check=None):
    return json.dumps({"narration": list(narration), "check": check, "changes": list(changes)})


def make_game(store, replies, die=15):
    provider = FakeProvider(replies, capabilities=Capabilities(schema_enforcement=True))
    factory = ProviderFactory({"providers": {"f": {"kind": "fake", "model": "m"}}, "tasks": {"default": {"provider": "f"}}},
                              env={}, builders={"fake": lambda spec, env: provider})
    return Game(store, factory, PromptBuilder.from_directory(), PLAYER_ID, D20Rules(FixedDice(die))), provider
