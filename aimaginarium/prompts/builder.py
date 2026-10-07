"""Builds prompts from recipes.

Stable content comes first (the system prompt), because providers cache by
prefix. Everything that changes between calls goes last, in the final user
message, after the conversation history.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from pydantic import BaseModel

from ..llm.base import Message, Request
from .fragments import FileFragmentSource, FragmentSource, PromptError, substitute
from .plan import NarrationPlan
from .recipes import Recipe, load_recipe
from .variants import Fixed, VariantPolicy

LIBRARY = Path(__file__).parent / "library"


@dataclass(frozen=True)
class Prompt:
    """A built prompt, ready to become a request.

    Attributes:
        recipe: Recipe id.
        task: The LLM task that runs it.
        variant: Variant used.
        system: The stable system prompt, including the narration plan.
        state: The volatile text that goes before the player's input.
        plan: The narration plan, or None if the reply has no narration.
        fragments: Fragment id to the hash of its text.
    """

    recipe: str
    task: str
    variant: str
    system: str
    state: str
    plan: Optional[NarrationPlan]
    fragments: Mapping[str, str]

    def request(
        self,
        history: Sequence[Message] = (),
        user_text: str = "",
        schema: Optional[type[BaseModel]] = None,
        **options: Any,
    ) -> Request:
        """Makes the request: system, history, then state and the player's input last.

        Args:
            history: Earlier turns, oldest first.
            user_text: What the player did or said this turn.
            schema: The reply model, or the base model whose fields follow the plan's narration.
            **options: Passed to :class:`Request` (``model``, ``temperature``).

        Returns:
            The request.
        """
        last = "\n\n".join(part for part in (self.state, user_text) if part)
        return Request(
            system=self.system,
            messages=(*history, Message("user", last)),
            schema=self.plan.reply_model(schema) if self.plan else schema,
            **options,
        )

    def record(self) -> dict[str, Any]:
        """Returns what to log so a call can be reproduced and compared."""
        return {"recipe": self.recipe, "variant": self.variant, "fragments": dict(self.fragments)}


class PromptBuilder:
    """Turns a recipe id and values into a :class:`Prompt`."""

    def __init__(
        self,
        fragments: FragmentSource,
        recipes_dir: Union[str, Path],
        policy: Optional[VariantPolicy] = None,
    ):
        """Initialises the builder.

        Args:
            fragments: Where fragment text comes from.
            recipes_dir: Directory of recipe TOML files.
            policy: Chooses variants; defaults to always ``base``.
        """
        self.fragments = fragments
        self.recipes_dir = Path(recipes_dir)
        self.policy = policy or Fixed()
        self._recipes: dict[str, Recipe] = {}

    @classmethod
    def from_directory(cls, root: Union[str, Path] = LIBRARY, policy: Optional[VariantPolicy] = None) -> "PromptBuilder":
        """Opens a library laid out as ``<root>/fragments`` and ``<root>/recipes``."""
        root = Path(root)
        return cls(FileFragmentSource(root / "fragments"), root / "recipes", policy)

    def recipe(self, recipe_id: str) -> Recipe:
        """Loads a recipe (once).

        Raises:
            PromptError: If there is no such recipe.
        """
        if recipe_id not in self._recipes:
            path = self.recipes_dir / f"{recipe_id}.toml"
            if not path.is_file():
                raise PromptError(f"unknown recipe {recipe_id!r}")
            self._recipes[recipe_id] = load_recipe(path)
        return self._recipes[recipe_id]

    def build(
        self,
        recipe_id: str,
        static: Optional[Mapping[str, Any]] = None,
        state: Optional[Mapping[str, Any]] = None,
        variant: Optional[str] = None,
    ) -> Prompt:
        """Builds a prompt.

        Args:
            recipe_id: Which recipe.
            static: Values for the stable fragments; they must not change from
                call to call, or the provider's cache is lost.
            state: Values for the volatile fragments and for placeholders in
                fragment ids (such as ``classification``).
            variant: A variant to force; otherwise the policy chooses.

        Returns:
            The prompt.

        Raises:
            PromptError: If a recipe, variant or fragment is unknown or a value is missing.
        """
        recipe = self.recipe(recipe_id)
        name = variant or self.policy.choose(recipe)
        layout = recipe.layout(name)
        static, state = static or {}, state or {}
        used: dict[str, str] = {}

        def render(ids: Sequence[str], values: Mapping[str, Any]) -> list[str]:
            parts = []
            for raw_id in ids:
                fragment = self.fragments.get(substitute(raw_id, values, f"fragment id {raw_id!r}"))
                used[fragment.id] = fragment.digest
                parts.append(fragment.render(values))
            return parts

        system = "\n\n".join([*render(layout.system, static), *([layout.plan.describe()] if layout.plan else [])])
        return Prompt(recipe.id, recipe.task, name, system, "\n\n".join(render(layout.state, state)), layout.plan, used)
