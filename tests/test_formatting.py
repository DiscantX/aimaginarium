"""Tests for terminal UI formatting and styling."""

from __future__ import annotations

from aimaginarium.ui.utils import format_assistant_message, format_player_message, colorize, set_stylesheet, Stylesheet


def test_format_assistant_message_basic():
    text = "Hello world."
    formatted = format_assistant_message(text, width=40)
    assert "↳" in formatted
    assert "Hello world." in formatted
    assert formatted.endswith("\n\n")


def test_format_player_message_basic():
    text = "\"Aye.\" I agree. I decide to take some hardtack."
    formatted = format_player_message(text, width=30)
    assert ">" in formatted
    assert "\"Aye.\" I agree." in formatted
    assert formatted.endswith("\n")


def test_format_assistant_message_multi_paragraph():
    text = "Paragraph one with enough text to wrap across multiple lines.\n\nParagraph two with enough text to wrap across multiple lines."
    formatted = format_assistant_message(text, width=30)
    lines = [line for line in formatted.splitlines() if line]
    # Verify we have multiple paragraphs / lines
    assert len(lines) > 2
    # Ensure no line starts with 4 spaces ("    ")
    for line in lines:
        # Strip ANSI escape sequences if present for indentation check
        plain = line
        while "\033[" in plain:
            start = plain.find("\033[")
            end = plain.find("m", start)
            if end != -1:
                plain = plain[:start] + plain[end+1:]
            else:
                break
        # If it's a wrapped line or second paragraph line, it should have at most 2 spaces indentation (excluding indicator)
        if not plain.startswith("↳"):
            # Check indentation spaces
            indent_spaces = len(plain) - len(plain.lstrip(" "))
            assert indent_spaces <= 2


def test_colorize_and_stylesheet():
    set_stylesheet({"styles": {"narration": "green", "indicator": "yellow"}})
    res = colorize("test", "narration")
    assert "\033[32m" in res
    assert "\033[0m" in res

    sheet = Stylesheet({"styles": {"indicator": "blue"}})
    assert sheet.get("indicator") == "blue"
    assert sheet.get("unknown") == "reset"
