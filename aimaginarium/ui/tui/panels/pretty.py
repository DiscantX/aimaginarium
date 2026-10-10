"""Readable views of trace payloads that never change what the payload says.

Pretty text shows a multi-line string as a block, one line per line of the string, with a dim ``↵`` where
each real newline is, so a newline cannot be mistaken for a space. :func:`raw` gives the exact JSON.
"""

import json
from typing import Any

from rich.text import Text

from ..hanging import Blocks, Hanging

NEWLINE = "↵"
BAR = "│ "


def raw(value: Any) -> str:
    """The exact JSON of a payload, newlines escaped as ``\\n``."""
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def pretty(value: Any) -> Blocks:
    """A readable rendering of a payload; strings with newlines become blocks with visible newline marks.

    Every line is its own :class:`~aimaginarium.ui.tui.hanging.Hanging` block, so a line that wraps keeps its
    indent (and, inside a multi-line string, its gutter) on every continuation line.
    """
    blocks: list[Hanging] = []
    _write(blocks, value, 0)
    return Blocks(blocks)


def _scalar(value: Any) -> Text:
    if isinstance(value, str):
        return Text(json.dumps(value, ensure_ascii=False), style="green")
    if value is None or isinstance(value, (bool, int, float)):
        return Text(json.dumps(value), style="yellow")
    if isinstance(value, (dict, list)):
        return Text(json.dumps(value))  # only an empty one gets here
    return Text(str(value))


def _write(blocks: list[Hanging], value: Any, level: int) -> None:
    pad = "  " * level
    if isinstance(value, dict) and value:
        items = value.items()
    elif isinstance(value, list) and value:
        items = ((f"[{i}]", item) for i, item in enumerate(value))
    elif isinstance(value, str) and "\n" in value:
        _block(blocks, value, level)
        return
    else:
        blocks.append(Hanging(_scalar(value), pad))
        return
    for key, item in items:
        label = Text(f"{key}:", style="bold")
        if isinstance(item, (dict, list)) and item:
            blocks.append(Hanging(label, pad))
            _write(blocks, item, level + 1)
        elif isinstance(item, str) and "\n" in item:
            blocks.append(Hanging(label, pad))
            _block(blocks, item, level + 1)
        else:
            blocks.append(Hanging(Text.assemble(label, " ", _scalar(item)), pad, pad + "  "))


def _block(blocks: list[Hanging], value: str, level: int) -> None:
    gutter = Text("  " * level + BAR, style="dim")
    lines = value.split("\n")
    for i, line in enumerate(lines):
        mark = Text(NEWLINE, style="dim") if i < len(lines) - 1 else Text()
        blocks.append(Hanging.gutter(Text.assemble(line, mark), gutter))
