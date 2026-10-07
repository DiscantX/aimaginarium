"""Prompt library: fragments and recipes that become requests for the LLM gateway."""

from .builder import LIBRARY, Prompt, PromptBuilder
from .fragments import FileFragmentSource, Fragment, FragmentSource, PromptError
from .plan import NarrationPlan, Slot
from .recipes import BASE, Layout, Recipe, load_recipe
from .variants import Fixed, PerSession, Pinned, VariantPolicy

__all__ = [
    "BASE", "FileFragmentSource", "Fixed", "Fragment", "FragmentSource", "LIBRARY", "Layout", "NarrationPlan",
    "PerSession", "Pinned", "Prompt", "PromptBuilder", "PromptError", "Recipe", "Slot", "VariantPolicy", "load_recipe",
]
