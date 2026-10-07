"""Policies that choose which variant of a recipe to use."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Mapping

from .recipes import BASE, Recipe


class VariantPolicy(ABC):
    """Chooses a variant for a recipe."""

    @abstractmethod
    def choose(self, recipe: Recipe) -> str:
        """Returns the name of a variant of ``recipe``."""


class Fixed(VariantPolicy):
    """Always the same variant when the recipe has it, else ``base``."""

    def __init__(self, name: str = BASE):
        self.name = name

    def choose(self, recipe: Recipe) -> str:
        """Returns the fixed variant if the recipe has one by that name."""
        return self.name if self.name in recipe.variants else BASE


class PerSession(VariantPolicy):
    """One variant per recipe for a whole session.

    The choice follows from the session id, so the same session always gets the
    same variants and a replay can reproduce them.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id

    def choose(self, recipe: Recipe) -> str:
        """Picks a variant from a hash of the session id and recipe id."""
        digest = hashlib.sha256(f"{self.session_id}:{recipe.id}".encode()).digest()
        return recipe.variants[int.from_bytes(digest[:4], "big") % len(recipe.variants)]


class Pinned(VariantPolicy):
    """Variants named per recipe, for replays and A/B runs; anything unnamed is ``base``."""

    def __init__(self, choices: Mapping[str, str]):
        self.choices = dict(choices)

    def choose(self, recipe: Recipe) -> str:
        """Returns the pinned variant for the recipe."""
        return self.choices.get(recipe.id, BASE)
