"""Prompt fragments: small pieces of prompt text stored as files.

A fragment is a markdown file. It may start with a front-matter block of
``key: value`` lines between ``---`` lines (for notes such as a description).
Placeholders are ``{name}``; braces that do not look like a name are left alone,
so JSON examples need no escaping.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Union

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class PromptError(Exception):
    """A prompt could not be built (unknown fragment or recipe, missing value, bad recipe)."""


def substitute(template: str, values: Mapping[str, Any], where: str = "") -> str:
    """Fills ``{name}`` placeholders.

    Args:
        template: Text with placeholders.
        values: Value for each name.
        where: What is being filled, for the error message.

    Returns:
        The filled text.

    Raises:
        PromptError: If a placeholder has no value.
    """
    missing = sorted({n for n in _PLACEHOLDER.findall(template) if n not in values})
    if missing:
        raise PromptError(f"{where or 'prompt'}: no value for {', '.join(missing)}")
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)


@dataclass(frozen=True)
class Fragment:
    """One piece of prompt text.

    Attributes:
        id: Where it lives, such as ``core/tenets``.
        text: The template, without front matter.
        meta: Front-matter fields.
    """

    id: str
    text: str
    meta: Mapping[str, str] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        """Returns a short hash of the template, to record which text a call used."""
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]

    def render(self, values: Mapping[str, Any]) -> str:
        """Returns the text with its placeholders filled."""
        return substitute(self.text, values, f"fragment {self.id!r}")


class FragmentSource(ABC):
    """Where fragments come from. Files now; a database layer of per-world overrides later."""

    @abstractmethod
    def get(self, fragment_id: str) -> Fragment:
        """Returns a fragment.

        Raises:
            PromptError: If there is no such fragment.
        """


def parse_fragment(fragment_id: str, raw: str) -> Fragment:
    """Splits front matter from the text of a fragment file."""
    meta: dict[str, str] = {}
    text = raw.replace("\r\n", "\n")
    if text.startswith("---\n"):
        head, sep, rest = text[4:].partition("\n---\n")
        if sep:
            for line in head.splitlines():
                key, _, value = line.partition(":")
                if value:
                    meta[key.strip()] = value.strip()
            text = rest
    return Fragment(fragment_id, text.strip(), meta)


class FileFragmentSource(FragmentSource):
    """Reads ``<root>/<id>.md``, with ids like ``core/tenets``."""

    def __init__(self, root: Union[str, Path]):
        """Initialises the source.

        Args:
            root: Directory holding the fragment files.
        """
        self.root = Path(root)

    def get(self, fragment_id: str) -> Fragment:
        """Reads one fragment file."""
        path = (self.root / f"{fragment_id}.md").resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise PromptError(f"unknown fragment {fragment_id!r}")
        return parse_fragment(fragment_id, path.read_text(encoding="utf-8"))

    def ids(self) -> list[str]:
        """Lists every fragment id."""
        return sorted(p.relative_to(self.root).with_suffix("").as_posix() for p in self.root.rglob("*.md"))
