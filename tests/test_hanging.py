"""Wrapped text keeps its indent: the helper itself, and every place that used to build layout into strings."""

import pytest

pytest.importorskip("textual")

from rich.console import Group  # noqa: E402
from rich.text import Text  # noqa: E402

from aimaginarium.ui.character import CharacterView  # noqa: E402
from aimaginarium.ui.tui.hanging import Hanging  # noqa: E402
from aimaginarium.ui.tui.panels.pretty import pretty  # noqa: E402
from layout_helpers import assert_hangs, render_lines  # noqa: E402

LONG = "A thick resin soaked branch meant for burning in dark places"


def test_every_wrapped_line_carries_the_prefix():
    assert_hangs(Hanging(LONG, "  "), "  ", LONG)


def test_a_bullet_hangs_under_its_text():
    lines = render_lines(Hanging(LONG, "• "), 20)
    assert lines[0].startswith("• ") and all(line.startswith("  ") for line in lines[1:])


def test_a_gutter_and_the_newline_mark_survive_wrapping():
    block = Hanging.gutter(Text.assemble(LONG, ("↵", "dim")), Text("│ ", style="dim"))
    for width in (14, 20):
        lines = render_lines(block, width)
        assert all(line.startswith("│ ") for line in lines)
        assert lines[-1].endswith("↵")                    # the mark stays at the end of the logical line


def test_real_newlines_start_new_logical_lines_that_carry_the_rest_prefix():
    assert render_lines(Hanging("one\ntwo", "> "), 20) == ["> one", "  two"]
    assert render_lines(Hanging.gutter("one\ntwo", "> "), 20) == ["> one", "> two"]


def test_plain_is_the_text_unwrapped():
    assert Hanging("a\nb", "• ").plain == "• a\n  b"


def test_a_multi_line_string_in_the_pretty_view_keeps_indent_and_gutter_when_wrapped():
    view = pretty({"system": LONG + "\nBe brief."})
    for width in (24, 31):
        lines = [line for line in render_lines(view, width) if line.strip()]
        assert lines[0] == "system:"
        assert all(line.startswith("  │ ") for line in lines[1:]), lines


def test_a_long_scalar_in_the_pretty_view_hangs_under_its_key():
    view = pretty({"a": {"note": LONG}})
    lines = [line for line in render_lines(view, 24) if line.strip()]
    assert lines[1].startswith("  note:") and all(line.startswith("    ") for line in lines[2:]), lines


def test_item_descriptions_and_about_bullets_in_the_character_panel_hang():
    from aimaginarium.ui.tui.character import CharacterPanel
    from textual.app import App
    from textual.widgets import Static

    from aimaginarium.ui.tui.theme import CANDLELIT, ROLE_DEFAULTS

    class Host(App):
        def get_theme_variable_defaults(self):
            return dict(ROLE_DEFAULTS)

        def compose(self):
            yield CharacterPanel()

    async def scenario():
        from aimaginarium.ui.character import Item
        async with Host().run_test(size=(40, 50)) as pilot:
            panel = pilot.app.query_one(CharacterPanel)
            panel.show(CharacterView(name="Kael", inventory=[Item(name="Resin-soaked torch", description=LONG)],
                                     facts=[LONG]))
            await pilot.pause()
            for key, prefix in (("inventory", "  "), ("about", "  ")):
                content = panel.query_one(f"#cp-{key}", Static).content
                lines = [line for line in render_lines(content, 24) if line.strip()]
                assert all(line.startswith(prefix) for line in lines[1:] if key == "inventory" or not line.startswith("•")), lines
                assert sum(line.startswith(prefix) for line in lines) >= 2

    import asyncio
    asyncio.run(scenario())
