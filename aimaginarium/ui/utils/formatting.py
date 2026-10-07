"""Terminal text formatting utilities for AImaginarium."""

from __future__ import annotations

import shutil
import textwrap
from typing import Optional

from .colors import colorize


def format_assistant_message(text: str, width: Optional[int] = None) -> str:
    """Formats an assistant narration message with '↳ ' indicator, block indentation, and trailing blank line.

    Args:
        text: The raw narration text from the LLM.
        width: Optional override for terminal width.

    Returns:
        The formatted text string ready to be printed.
    """
    if not text:
        return ""
    term_width = width or shutil.get_terminal_size().columns
    paragraphs = text.split("\n\n")
    formatted_paragraphs = []
    for i, para in enumerate(paragraphs):
        para_clean = para.strip()
        if not para_clean:
            continue
        wrapped = textwrap.fill(
            para_clean,
            width=term_width,
            initial_indent="",
            subsequent_indent="  ",
            break_long_words=False,
        )
        styled_body = colorize(wrapped, "narration")
        lines = styled_body.splitlines()

        if i == 0:
            ind = colorize("↳ ", "indicator")
            if lines:
                lines[0] = ind + lines[0]
        else:
            lines = ["  " + line for line in lines]

        formatted_paragraphs.append("\n".join(lines))

    body = "\n\n".join(formatted_paragraphs)
    return f"{body}\n\n"
