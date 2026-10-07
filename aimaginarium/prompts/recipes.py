"""Recipes: which fragments make up a prompt for one situation, and its variants.

A recipe file (TOML)::

    id = "opening"
    task = "opening"            # which LLM task runs it (see the factory)
    system = ["core/role"]      # stable fragments, first, so providers can cache them
    state = ["state/scene"]     # fragments that change every call, placed last

    [[plan]]
    id = "world"
    count = 3
    instruction = "Give an overview of the world."

    [variants.terse]            # replaces any of system, state and plan
    system = ["core/role", "style/terse"]

Fragment ids may hold placeholders (``outcome/{classification}``), filled from
the state values when the prompt is built.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .fragments import PromptError
from .plan import NarrationPlan, Slot

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

BASE = "base"


@dataclass(frozen=True)
class Layout:
    """What a prompt is made of.

    Attributes:
        system: Ids of the stable fragments.
        state: Ids of the volatile fragments.
        plan: The narration plan.
    """

    system: tuple[str, ...]
    state: tuple[str, ...]
    plan: NarrationPlan


@dataclass(frozen=True)
class Recipe:
    """A prompt recipe and its variants.

    Attributes:
        id: Recipe name.
        task: The LLM task that runs it.
        base: The default layout.
        overrides: Variant name to the fields that variant replaces.
    """

    id: str
    task: str
    base: Layout
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @property
    def variants(self) -> list[str]:
        """Returns every variant name, ``base`` first."""
        return [BASE, *sorted(self.overrides)]

    def layout(self, variant: str = BASE) -> Layout:
        """Returns the layout of a variant.

        Raises:
            PromptError: If the recipe has no such variant.
        """
        if variant == BASE:
            return self.base
        if variant not in self.overrides:
            raise PromptError(f"recipe {self.id!r} has no variant {variant!r}")
        return _layout(self.overrides[variant], self.base)


def _plan(raw: list[Mapping[str, Any]]) -> NarrationPlan:
    """Reads ``[[plan]]`` tables; ``count`` means a fixed number of paragraphs."""
    slots = []
    for entry in raw:
        low = entry.get("count", entry.get("min", 1))
        slots.append(Slot(entry["id"], entry["instruction"], low, entry.get("max", entry.get("count"))))
    return NarrationPlan(slots)


def _layout(raw: Mapping[str, Any], base: Optional[Layout] = None) -> Layout:
    """Reads a layout, taking anything the table leaves out from ``base``."""
    system = tuple(raw["system"]) if "system" in raw else getattr(base, "system", None)
    state = tuple(raw["state"]) if "state" in raw else getattr(base, "state", ())
    plan = _plan(raw["plan"]) if "plan" in raw else getattr(base, "plan", None)
    if system is None or plan is None:
        raise PromptError("a recipe needs 'system' and a 'plan'")
    return Layout(system, state, plan)


def parse_recipe(raw: Mapping[str, Any]) -> Recipe:
    """Builds a recipe from a parsed TOML mapping."""
    try:
        return Recipe(raw["id"], raw.get("task", raw["id"]), _layout(raw), dict(raw.get("variants", {})))
    except KeyError as exc:
        raise PromptError(f"recipe is missing {exc}") from exc


def load_recipe(path: Union[str, Path]) -> Recipe:
    """Reads a recipe file.

    Raises:
        PromptError: If the file is not valid TOML or not a valid recipe.
    """
    try:
        return parse_recipe(tomllib.loads(Path(path).read_text(encoding="utf-8")))
    except tomllib.TOMLDecodeError as exc:
        raise PromptError(f"{path} is not valid TOML: {exc}") from exc
