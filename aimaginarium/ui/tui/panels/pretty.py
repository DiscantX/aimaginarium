"""Readable views of trace payloads that never change what the payload says.

Pretty text shows a multi-line string as a block, one line per line of the string, with a dim ``↵`` where
each real newline is, so a newline cannot be mistaken for a space. :func:`raw` gives the exact JSON.
"""

import json
from typing import Any

from rich.text import Text

NEWLINE = "↵"
BAR = "│ "


def raw(value: Any) -> str:
    """The exact JSON of a payload, newlines escaped as ``\\n``."""
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def pretty(value: Any) -> Text:
    """A readable rendering of a payload; strings with newlines become blocks with visible newline marks."""
    text = Text()
    _write(text, value, 0)
    text.rstrip()
    return text


def _scalar(text: Text, value: Any) -> None:
    if isinstance(value, str):
        text.append(json.dumps(value, ensure_ascii=False), style="green")
    elif value is None or isinstance(value, (bool, int, float)):
        text.append(json.dumps(value), style="yellow")
    else:
        text.append(str(value))


def _write(text: Text, value: Any, level: int) -> None:
    pad = "  " * level
    if isinstance(value, dict) and value:
        items = value.items()
    elif isinstance(value, list) and value:
        items = ((f"[{i}]", item) for i, item in enumerate(value))
    else:
        text.append(pad)
        _block_or_scalar(text, value, level)
        return
    for key, item in items:
        text.append(f"{pad}{key}:", style="bold")
        if isinstance(item, (dict, list)) and item:
            text.append("\n")
            _write(text, item, level + 1)
        elif isinstance(item, str) and "\n" in item:
            text.append("\n")
            _block(text, item, level + 1)
        else:
            text.append(" ")
            _scalar(text, item if not isinstance(item, (dict, list)) else json.dumps(item))
            text.append("\n")


def _block_or_scalar(text: Text, value: Any, level: int) -> None:
    if isinstance(value, str) and "\n" in value:
        text.append("\n")
        _block(text, value, level)
    else:
        _scalar(text, value if not isinstance(value, (dict, list)) else json.dumps(value))
        text.append("\n")


def _block(text: Text, value: str, level: int) -> None:
    pad = "  " * level
    lines = value.split("\n")
    for i, line in enumerate(lines):
        text.append(pad + BAR, style="dim")
        text.append(line)
        if i < len(lines) - 1:
            text.append(NEWLINE, style="dim")
        text.append("\n")
