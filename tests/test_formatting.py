"""Tests for terminal UI formatting and styling."""

from __future__ import annotations

from aimaginarium.ui.utils import format_assistant_message, colorize, set_stylesheet, Stylesheet


def test_format_assistant_message_basic():
    text = "Hello world."
    formatted = format_assistant_message(text, width=40)
    assert "↳" in formatted
    assert "Hello world." in formatted
    assert formatted.endswith("\n\n")


def test_colorize_and_stylesheet():
    set_stylesheet({"styles": {"narration": "green", "indicator": "yellow"}})
    res = colorize("test", "narration")
    assert "\033[32m" in res
    assert "\033[0m" in res

    sheet = Stylesheet({"styles": {"indicator": "blue"}})
    assert sheet.get("indicator") == "blue"
    assert sheet.get("unknown") == "reset"
