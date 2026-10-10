"""Parsing of the dev-note command, shared by every client.

``/dn [turn] [#tag ...] text`` (also ``/dev-note``) attaches a dev note to a turn: the latest when no turn is
given. A dev note is the developer's remark about the game, kept outside it; it is not a player note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMANDS = ("/dn", "/dev-note")
"""The names the command answers to."""

USAGE = "Usage: /dn [turn] [#tag ...] what you noticed"

_TAG = re.compile(r"#([A-Za-z][\w-]*)")


@dataclass(frozen=True)
class ParsedNote:
    """What the command line said: the turn (None for the latest), the tags and the text."""

    turn: int | None
    tags: tuple[str, ...]
    text: str


def parse(args: str) -> ParsedNote:
    """Parses the part of the line after the command name.

    A leading whole number is the turn. A word like ``#continuity`` is a tag (taken out of the text; ``#12`` is
    not a tag). Tags are lower-cased and kept once, in order.

    Raises:
        ValueError: If there is no text, with the usage line as its message.
    """
    words = args.split()
    turn = None
    if words and words[0].isdigit():
        turn = int(words.pop(0))
    tags: list[str] = []
    kept: list[str] = []
    for word in words:
        match = _TAG.fullmatch(word)
        if match:
            tag = match.group(1).lower()
            if tag not in tags:
                tags.append(tag)
        else:
            kept.append(word)
    if not kept:
        raise ValueError(USAGE)
    return ParsedNote(turn, tuple(tags), " ".join(kept))


def confirmation(note: dict) -> str:
    """The line a client shows after a note was saved."""
    return f"Dev note {note['id']} added to turn {note['turn_id']}."
