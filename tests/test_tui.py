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
from engine_helpers import make_game, reply, stealth_check  # noqa: E402


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
