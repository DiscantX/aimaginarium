"""Tests for the selectable payload views of the dev dock (#90) and their pretty / JSON modes (#91)."""

import json
import logging

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, Static, TabbedContent  # noqa: E402

from aimaginarium.api import Role  # noqa: E402
from aimaginarium.ui.tui.panels.log import LogPane  # noqa: E402
from aimaginarium.ui.tui.panels.state import StateInspector  # noqa: E402
from aimaginarium.ui.tui.panels.trace import TraceTimeline  # noqa: E402
from aimaginarium.ui.tui.views import ModeBar, PayloadView, SelectableText, layout  # noqa: E402
from test_tui import act, instant, make_app, run, until  # noqa: E402,F401  (instant is an autouse fixture)
from engine_helpers import reply  # noqa: E402


def body(view) -> Static:
    return view.query_one(SelectableText).query_one(Static)


async def drag(pilot, widget, start=(0, 0), end=(12, 1)):
    await pilot.mouse_down(widget, offset=start)
    await pilot.hover(widget, offset=end)
    await pilot.mouse_up(widget, offset=end)
    await pilot.pause()


async def open_state(app, pilot) -> PayloadView:
    app.query_one(TabbedContent).active = "tab-stateinspector"
    await pilot.pause(0.4)
    view = app.query_one(StateInspector).query_one(PayloadView)
    await until(pilot, lambda: view.displayed)
    return view


def test_the_state_view_selects_and_copies_exactly_the_text_shown():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            view = await open_state(app, pilot)
            await drag(pilot, body(view))
            selected = app.screen.get_selected_text()
            assert selected and "\n" in selected and "│" in selected          # the gutter is on screen, so it is selected
            assert view.displayed.startswith(selected)                       # nothing added, nothing taken out
            assert "View:" not in selected                                   # the mode bar is not content
    run(scenario)


def test_the_json_mode_selects_the_exact_json_text():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            view = await open_state(app, pilot)
            app.query_one(StateInspector).query_one("#player").value = True
            await pilot.pause(0.3)
            app.set_payload_mode("json")
            await pilot.pause(0.3)
            assert view.displayed.startswith("{") and json.loads(view.shown) == view.value
            await drag(pilot, body(view), end=(6, 1))
            selected = app.screen.get_selected_text()
            assert selected and view.displayed.startswith(selected) and selected.startswith("{")
    run(scenario)


def test_the_trace_detail_text_can_be_selected():
    async def scenario():
        app = make_app([reply(["Marta smiles."])], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "I greet Marta.")
            await until(pilot, lambda: app.query_one(TraceTimeline).shown)
            detail = app.query_one(TraceTimeline).query_one(PayloadView)
            await until(pilot, lambda: detail.displayed)
            await drag(pilot, body(detail), end=(10, 0))
            assert app.screen.get_selected_text() and detail.displayed.startswith(app.screen.get_selected_text())
    run(scenario)


def test_a_view_says_which_mode_it_is_in_and_p_switches_every_view_together():
    async def scenario():
        app = make_app([reply(["Marta smiles."])], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "I greet Marta.")
            timeline = app.query_one(TraceTimeline)
            await until(pilot, lambda: timeline.shown)
            state = app.query_one(StateInspector).query_one(PayloadView)
            bar = timeline.query_one(ModeBar)
            assert "Pretty" in bar.plain and "(p switches)" in bar.plain
            assert "↵" in timeline.shown
            timeline.query_one(DataTable).focus()
            await pilot.press("p")
            await pilot.pause(0.2)
            assert app.payload_mode == "json" and "↵" not in timeline.shown and "\\n" in timeline.shown
            assert state.mode == "json" and json.loads(state.shown) == state.value      # every view followed
            await pilot.press("p")
            await pilot.pause(0.2)
            assert app.payload_mode == "pretty" and "↵" in timeline.shown
    run(scenario)


def test_clicking_a_mode_name_switches_the_mode():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            view = await open_state(app, pilot)
            bar = view.query_one(ModeBar)
            column = bar.plain.index("JSON") + 1
            await pilot.click(bar, offset=(column + 1, 0))                      # +1 for the bar's padding
            await pilot.pause(0.2)
            assert app.payload_mode == "json" and view.mode == "json"
            column = bar.plain.index("Pretty") + 1
            await pilot.click(bar, offset=(column + 1, 0))
            await pilot.pause(0.2)
            assert app.payload_mode == "pretty"
    run(scenario)


def test_p_is_offered_only_where_a_payload_is_shown_and_c_still_copies_the_exact_json():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            view = await open_state(app, pilot)
            state, log = app.query_one(StateInspector), app.query_one(LogPane)
            assert state.check_action("toggle_view", ()) and not log.check_action("toggle_view", ())
            assert json.loads(state.copy_text()) == view.value                  # the raw JSON, whatever the mode
    run(scenario)


def test_the_log_text_can_be_selected_and_a_wrapped_record_stays_indented():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one(TabbedContent).active = "tab-logpane"
            await pilot.pause(0.3)
            pane = app.query_one(LogPane)
            logging.getLogger("aimaginarium.tui").warning("word " * 60)
            view = pane.query_one(SelectableText)
            await until(pilot, lambda: "word word" in view.displayed)
            lines = view.displayed.split("\n")
            record = [i for i, line in enumerate(lines) if "WARNING" in line][0]
            assert lines[record + 1].startswith("    ")                          # the continuation hangs
            await drag(pilot, view.query_one(Static), start=(0, record), end=(20, record))
            assert view.displayed.split("\n")[record].startswith(app.screen.get_selected_text().rstrip())
    run(scenario)


def test_layout_cuts_to_the_width_and_keeps_styles():
    from rich.text import Text
    content = layout(Text("alpha beta gamma delta", style="bold"), 11)
    assert content.plain == "alpha beta\ngamma delta"
    assert layout(None, 20).plain == "" and layout(Text("x"), 0).plain == ""
