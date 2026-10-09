"""Tests for the Textual UI, driven by Textual's pilot against the scripted fake provider."""

import asyncio

import pytest

pytest.importorskip("textual")

from textual import events  # noqa: E402

from aimaginarium.api import LocalServer, Role, RollResult  # noqa: E402
from aimaginarium.engine import create_demo_world  # noqa: E402
from aimaginarium.ui.tui import GameApp  # noqa: E402
from aimaginarium.ui.tui.inputs import ActionInput, PasteConfirm  # noqa: E402
from aimaginarium.ui.tui.roll import RollScreen  # noqa: E402
from aimaginarium.ui.tui.runner import roll_line  # noqa: E402
from aimaginarium.ui.tui.thinking import Thinking  # noqa: E402
from aimaginarium.world import WorldStore  # noqa: E402
from engine_helpers import PLAYER_ID, make_game, reply, stealth_check  # noqa: E402
from aimaginarium.ui.tui.panels import DevPanel  # noqa: E402
from aimaginarium.ui.tui.panels.events import ChecksPanel, DiffPanel  # noqa: E402
from aimaginarium.ui.tui.panels.log import LogPane  # noqa: E402
from aimaginarium.ui.tui.panels.state import StateInspector  # noqa: E402
from aimaginarium.ui.tui.panels.trace import TraceTimeline  # noqa: E402
from textual.widgets import DataTable, RadioButton, Tree  # noqa: E402


CREATE = [{"op": "create", "ref": "@coin", "kind": "item", "name": "Silver coin", "parent_id": PLAYER_ID}]


@pytest.fixture(autouse=True)
def instant(monkeypatch):
    """No waiting in the roll window, so a scenario runs as fast as the events arrive."""
    monkeypatch.setattr(RollScreen, "min_spin", 0.0)


def make_app(replies, die=15, opening=False, role=Role.PLAYER, auto_close=True):
    store = WorldStore.open()
    create_demo_world(store)
    game = make_game(store, replies, die)[0]
    app = GameApp(LocalServer(game, dev_enabled=True).connect(role), opening=opening)
    app.settings.roll_auto_close, app.settings.roll_hold = auto_close, 0.0
    app.animation_level = "none"  # Textual reads TEXTUAL_ANIMATIONS once at import, so set it on the app itself
    return app


async def until(pilot, condition, tries=200):
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.02)
    raise AssertionError("condition never became true")


def texts(app, kind):
    return [e.text for e in app.story.entries(kind)]


async def act(pilot, text):
    pilot.app.query_one(ActionInput).value = text
    await pilot.press("enter")


def run(scenario):
    asyncio.run(scenario())


def test_the_opening_scene_is_narrated():
    async def scenario():
        app = make_app([reply(["Marta nods."])], opening=True)
        async with app.run_test() as pilot:
            await until(pilot, lambda: texts(app, "narration"))
            assert texts(app, "narration") == ["Marta nods."]
    run(scenario)


def test_an_action_shows_the_players_line_then_the_narration():
    async def scenario():
        app = make_app([reply(["Marta smiles."])])
        async with app.run_test() as pilot:
            await act(pilot, "I greet Marta.")
            await until(pilot, lambda: texts(app, "narration"))
            assert texts(app, "player") == ["> I greet Marta."]
            assert texts(app, "narration") == ["Marta smiles."]
            await until(pilot, lambda: not app.query_one(ActionInput).disabled)
    run(scenario)


def test_a_check_opens_the_roll_modal_and_the_roll_lands_in_the_log():
    async def scenario():
        app = make_app([reply(["You creep."], check=stealth_check()), reply(["You slip past."])], die=14)
        async with app.run_test() as pilot:
            await act(pilot, "I sneak.")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            assert app.screen.check.skill == "stealth" and app.screen.check.difficulty == 12
            await pilot.click("#button")
            await until(pilot, lambda: texts(app, "narration") == ["You creep.", "You slip past."]
                        and not isinstance(app.screen, RollScreen))
            assert texts(app, "roll") == ["Stealth: rolled 14 +1 = 15 against 12, success"]
            kinds = [e.kind for e in app.story.entries() if e.kind != "player"]
            assert kinds == ["narration", "roll", "narration"]
    run(scenario)


def test_the_roll_line_uses_the_engines_ruling_not_the_total():
    assert roll_line(RollResult("climb", 3, 1, 4, 10, "failure")).endswith("against 10, failure")
    # a natural 1 is a critical failure even though the total meets the difficulty
    assert roll_line(RollResult("climb", 1, 9, 10, 10, "critical_failure")).endswith("critical failure")
    assert roll_line(RollResult("climb", 12, 0, 12, 10, "narrow_success")).endswith("narrow success")


def test_thinking_shows_a_frame_and_a_message_while_it_runs():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            thinking = app.query_one(Thinking)
            assert not thinking.running
            thinking.start()
            await pilot.pause(0.2)
            assert thinking.running and "..." in str(thinking.render())
            thinking.stop()
            assert not thinking.running
    run(scenario)


def test_the_dev_role_can_preview_a_roll_without_touching_the_game():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            await act(pilot, "/roll climb 2 1")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            assert (app.screen.check.skill, app.screen.check.difficulty) == ("climb", 2)
            await pilot.click("#button")
            await until(pilot, lambda: texts(app, "roll") and not isinstance(app.screen, RollScreen))
            assert texts(app, "roll")[0].startswith("[preview] Climb: rolled 1 +")
            assert texts(app, "roll")[0].endswith("critical failure")
            assert not texts(app, "narration") and not texts(app, "system")
    run(scenario)


def test_a_bad_preview_is_explained_and_the_player_role_has_no_preview():
    async def scenario():
        dev = make_app([], role=Role.DEV)
        async with dev.run_test() as pilot:
            await act(pilot, "/roll climb x")
            await until(pilot, lambda: texts(dev, "system"))
            assert texts(dev, "system")[0].startswith("Usage: /roll")
        player = make_app([])
        async with player.run_test() as pilot:
            await act(pilot, "/roll")
            await until(pilot, lambda: texts(player, "system"))
            assert texts(player, "system") == ["Unknown command /roll."]
    run(scenario)


def test_a_small_paste_goes_straight_in():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            app.query_one(ActionInput).post_message(events.Paste("short text"))
            await pilot.pause()
            assert app.query_one(ActionInput).value == "short text"
    run(scenario)


def test_a_large_paste_asks_first_and_can_be_declined():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            app.query_one(ActionInput).post_message(events.Paste("line one\nline two"))
            await until(pilot, lambda: isinstance(app.screen, PasteConfirm))
            assert app.query_one(ActionInput).value == ""
            await pilot.click("#cancel")
            await until(pilot, lambda: not isinstance(app.screen, PasteConfirm))
            assert app.query_one(ActionInput).value == ""
    run(scenario)


def test_a_confirmed_paste_becomes_one_line():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            app.query_one(ActionInput).post_message(events.Paste("line one\nline two"))
            await until(pilot, lambda: isinstance(app.screen, PasteConfirm))
            await pilot.click("#paste")
            await until(pilot, lambda: app.query_one(ActionInput).value)
            assert app.query_one(ActionInput).value == "line one line two"
    run(scenario)


def test_unknown_slash_commands_are_noted_and_quit_leaves():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            await act(pilot, "/nope")
            await until(pilot, lambda: texts(app, "system"))
            assert texts(app, "system") == ["Unknown command /nope."]
            await act(pilot, "/quit")
            await until(pilot, lambda: app._exit)
    run(scenario)


def test_by_default_the_roll_window_waits_for_the_player():
    async def scenario():
        app = make_app([reply(["You creep."], check=stealth_check()), reply(["You slip past."])], die=14,
                       auto_close=False)
        async with app.run_test() as pilot:
            await act(pilot, "I sneak.")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            await pilot.click("#button")
            await until(pilot, lambda: app.screen.phase == "shown" and str(app.screen.query_one("#button").label)
                        == "Continue")
            await pilot.press("a", "b", "x")           # typing does not dismiss it
            await pilot.pause(0.2)
            assert isinstance(app.screen, RollScreen)
            await pilot.click("#button")
            await until(pilot, lambda: texts(app, "narration") == ["You creep.", "You slip past."]
                        and not isinstance(app.screen, RollScreen))
    run(scenario)


def test_the_roll_window_closes_by_itself_when_auto_close_is_on():
    async def scenario():
        app = make_app([reply(["You creep."], check=stealth_check()), reply(["You slip past."])], die=14)
        async with app.run_test() as pilot:
            await act(pilot, "I sneak.")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            await pilot.press("r")
            await until(pilot, lambda: not isinstance(app.screen, RollScreen) and len(texts(app, "narration")) == 2)
    run(scenario)


def test_the_die_slows_into_the_final_faces():
    """Faces land at t = 1 - (1 - i/N)^(1/ramp): the first gap is brisk and the last is long and clearly slower."""
    n, ramp, total = 30, RollScreen.ramp, RollScreen.tumble
    times = [total * (1 - (1 - i / n) ** (1 / ramp)) for i in range(n + 1)]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps[0] < 0.08 and gaps[-1] > 0.4
    assert gaps[-1] > 2 * gaps[-2] and all(b >= a for a, b in zip(gaps, gaps[1:]))


def test_the_dev_dock_exists_only_for_the_dev_role():
    async def scenario():
        player = make_app([])
        async with player.run_test():
            assert not player.query(DevPanel) and not player.query("#dev-dock")
        dev = make_app([], role=Role.DEV)
        async with dev.run_test():
            assert {type(p) for p in dev.query(DevPanel)} == {TraceTimeline, StateInspector, DiffPanel, ChecksPanel,
                                                              LogPane}
    run(scenario)


def test_a_turn_fills_the_trace_the_diffs_and_the_checks():
    async def scenario():
        app = make_app([reply(["You creep."], check=stealth_check()), reply(["You slip past."], changes=CREATE)],
                       die=14, role=Role.DEV)
        async with app.run_test() as pilot:
            await act(pilot, "I sneak.")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            await pilot.press("r")
            await until(pilot, lambda: len(texts(app, "narration")) == 2 and not isinstance(app.screen, RollScreen))
            await until(pilot, lambda: len(app.query_one(DiffPanel).query_one(Tree).root.children) == 1)
            kinds = [e.kind for e in app.query_one(TraceTimeline).records.values()]
            assert {"llm.call", "check.workings", "changes.accepted", "state.diff"} <= set(kinds)
            assert app.query_one(TraceTimeline).query_one(DataTable).row_count == len(kinds)
            check = app.query_one(ChecksPanel).query_one(Tree).root.children[0]
            assert check.data["skill"] == "stealth" and check.data["difficulty"] == 12
            assert any("creaking floor" in leaf.data for leaf in check.children)
            diff = app.query_one(DiffPanel).query_one(Tree).root.children[0]
            assert any(leaf.data["kind"] == "entity.create" or "create" in leaf.data["kind"] for leaf in diff.children)
    run(scenario)


def test_the_state_inspector_shows_the_gm_view_and_the_players_projection():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            inspector = app.query_one(StateInspector)
            await until(pilot, lambda: "[char-2]" in inspector.raw)                 # the GM sees entity ids
            inspector.query_one("#player", RadioButton).value = True
            await until(pilot, lambda: "[char-2]" not in inspector.raw and "location" in inspector.raw.lower())
    run(scenario)


def test_undo_greys_the_turn_out_for_the_dev_role_and_removes_it_otherwise():
    async def scenario():
        app = make_app([reply(["Marta smiles."])], role=Role.DEV)
        async with app.run_test() as pilot:
            await act(pilot, "I greet Marta.")
            await until(pilot, lambda: texts(app, "narration") and not app.query_one(ActionInput).disabled)
            assert all(e.turn_id == 1 for e in app.story.entries() if e.kind in ("player", "narration"))
            await act(pilot, "/undo")
            await until(pilot, lambda: all(e.has_class("retracted") for e in app.story.entries()))
            assert len(app.story.entries()) == 2                                  # still shown, greyed out
        player = make_app([reply(["Marta smiles."])])
        async with player.run_test() as pilot:
            await act(pilot, "I greet Marta.")
            await until(pilot, lambda: texts(player, "narration") and not player.query_one(ActionInput).disabled)
            player.story.retract(1, remove=True)
            await until(pilot, lambda: not player.story.entries())
    run(scenario)


def test_undo_with_nothing_to_take_back_says_so():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            await act(pilot, "/undo")
            await pilot.pause(0.2)
            assert app._notifications and "no turn" in app._notifications.__iter__().__next__().message.lower()
    run(scenario)


def test_the_log_pane_filters_by_level_and_component():
    import logging
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            pane = app.query_one(LogPane)
            logging.getLogger("aimaginarium.llm.retry").debug("quiet detail")
            logging.getLogger("aimaginarium.llm.retry").warning("slow reply")
            logging.getLogger("aimaginarium.engine").error("bad change")
            await until(pilot, lambda: len(pane.shown) == 2)                       # debug is below the Info default
            assert "slow reply" in pane.shown[0] and "bad change" in pane.shown[1]
            pane.query_one("#component").value = "engine"
            await until(pilot, lambda: len(pane.shown) == 1)
            assert "bad change" in pane.shown[0]
    run(scenario)


def test_the_state_inspector_follows_an_undo():
    async def scenario():
        app = make_app([reply(["You find a coin."], changes=CREATE)], role=Role.DEV)
        async with app.run_test() as pilot:
            inspector = app.query_one(StateInspector)
            await act(pilot, "I look.")
            await until(pilot, lambda: "Silver coin" in inspector.raw)
            await act(pilot, "/undo")
            await until(pilot, lambda: "Silver coin" not in inspector.raw and "[char-2]" in inspector.raw)
    run(scenario)


def test_the_palette_offers_dev_commands_only_to_the_dev_role():
    from textual.widgets import OptionList

    async def entries(role):
        app = make_app([], role=role)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+p")
            await pilot.pause(0.4)
            options = app.screen.query(OptionList).first()
            return [str(options.get_option_at_index(i).prompt) for i in range(options.option_count)]

    async def scenario():
        dev, player = await entries(Role.DEV), await entries(Role.PLAYER)
        assert any(e.startswith("Undo last turn") for e in dev) and any(e.startswith("Preview a roll") for e in dev)
        assert not any("Undo" in e or "Preview a roll" in e for e in player)
    run(scenario)


def test_every_dev_tab_draws_without_crashing():
    """Hidden tabs are never drawn, so a bug in a panel's drawing only shows when its tab is opened."""
    from textual.widgets import TabbedContent

    async def scenario():
        app = make_app([reply(["You creep."], check=stealth_check()), reply(["You slip past."], changes=CREATE)],
                       die=14, role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "I sneak.")
            await until(pilot, lambda: isinstance(app.screen, RollScreen))
            await pilot.press("r")
            await until(pilot, lambda: len(texts(app, "narration")) == 2 and not isinstance(app.screen, RollScreen))
            dock = app.query_one(TabbedContent)
            for pane in dock.query("TabPane"):
                dock.active = pane.id
                await pilot.pause(0.3)
                app.export_screenshot()                                           # forces a full draw
            assert dock.active == "tab-logpane"
    run(scenario)


def test_the_trace_table_and_detail_can_be_resized_by_dragging_the_splitter():
    from textual_widgets import HorizontalSplitter

    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            timeline = app.query_one(TraceTimeline)
            table, splitter = timeline.query_one("#trace-rows"), timeline.query_one(HorizontalSplitter)
            before = table.outer_size.height
            x, y = splitter.region.x + 5, splitter.region.y
            await pilot.mouse_down(None, offset=(x, y))
            await pilot.hover(None, offset=(x, y + 4))
            await pilot.mouse_up(None, offset=(x, y + 4))
            await pilot.pause()
            assert table.outer_size.height == before + 4
    run(scenario)


def test_pretty_shows_newlines_as_visible_blocks_and_raw_keeps_them_escaped():
    from aimaginarium.ui.tui.panels.pretty import pretty, raw
    payload = {"system": "You are the GM.\nBe brief.", "model": "m", "n": 3, "messages": [{"role": "user", "content": "a\nb"}]}
    text = pretty(payload).plain
    assert "system:\n  │ You are the GM.↵\n  │ Be brief." in text      # real newlines, each marked
    assert 'model: "m"' in text and "n: 3" in text and "[0]:" in text
    assert "\\n" in raw(payload) and "↵" not in raw(payload)            # raw is the exact JSON


def test_the_trace_detail_switches_between_pretty_and_raw_and_copies_the_raw_json():
    async def scenario():
        app = make_app([reply(["Marta smiles."])], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "I greet Marta.")
            await until(pilot, lambda: texts(app, "narration"))
            timeline = app.query_one(TraceTimeline)
            await until(pilot, lambda: timeline.selected is not None and timeline.shown)
            assert "↵" in timeline.shown and "│ " in timeline.shown            # the prompt reads as blocks
            timeline.query_one(DataTable).focus()
            await pilot.press("p")
            assert "↵" not in timeline.shown and "\\n" in timeline.shown       # raw: exact JSON, escaped
            assert "\\n" in timeline.copy_text()
    run(scenario)


def test_diff_and_check_lines_are_cut_to_the_panel_width_and_the_full_entry_shows_below():
    from aimaginarium.ui.tui.panels.events import fit
    assert fit("a  b\nc", 20) == "a b c" and fit("x" * 50, 10) == "x" * 9 + "…"

    async def scenario():
        app = make_app([reply(["You find a coin."], changes=CREATE)], role=Role.DEV)
        async with app.run_test(size=(120, 40)) as pilot:
            await act(pilot, "I look.")
            panel = app.query_one(DiffPanel)
            await until(pilot, lambda: panel.query_one(Tree).root.children)
            from textual.widgets import TabbedContent
            app.query_one(TabbedContent).active = "tab-diffpanel"                 # a hidden tab has no width yet
            await pilot.pause(0.4)
            leaf = panel.query_one(Tree).root.children[0].children[0]
            assert len(str(leaf.label)) <= panel.query_one(Tree).size.width
            panel.query_one(Tree).move_cursor(leaf)
            await until(pilot, lambda: "Silver coin" in panel.shown)
    run(scenario)


def test_the_state_tab_toggle_does_not_take_over_the_panel():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            from textual.widgets import TabbedContent
            app.query_one(TabbedContent).active = "tab-stateinspector"
            await pilot.pause(0.3)
            assert app.query_one(StateInspector).query_one(".toggle").outer_size.height <= 3
    run(scenario)


def test_the_log_tab_receives_records_from_any_logger_and_the_dev_log_command():
    import logging
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            pane = app.query_one(LogPane)
            logging.getLogger("httpx").info("HTTP Request: POST https://example.test 200 OK")   # a library, not ours
            await act(pilot, "/log warning something odd")
            await until(pilot, lambda: len(pane.shown) == 2)
            assert "httpx" in pane.shown[0] and "something odd" in pane.shown[1]
    run(scenario)
