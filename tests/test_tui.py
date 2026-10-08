"""Tests for the Textual UI, driven by Textual's pilot against the scripted fake provider."""

import asyncio

import pytest

pytest.importorskip("textual")

from textual import events  # noqa: E402

from aimaginarium.api import LocalServer  # noqa: E402
from aimaginarium.engine import create_demo_world  # noqa: E402
from aimaginarium.ui.tui import GameApp  # noqa: E402
from aimaginarium.ui.tui.inputs import ActionInput, PasteConfirm  # noqa: E402
from aimaginarium.ui.tui.roll import RollScreen  # noqa: E402
from aimaginarium.ui.tui.runner import roll_line  # noqa: E402
from aimaginarium.world import WorldStore  # noqa: E402
from engine_helpers import make_game, reply, stealth_check  # noqa: E402


@pytest.fixture(autouse=True)
def instant(monkeypatch):
    """No animation and no holding, so a scenario runs as fast as the events arrive."""
    monkeypatch.setenv("TEXTUAL_ANIMATIONS", "none")
    monkeypatch.setattr(RollScreen, "hold", 0.0)


def make_app(replies, die=15, opening=False):
    store = WorldStore.open()
    create_demo_world(store)
    game = make_game(store, replies, die)[0]
    return GameApp(LocalServer(game).connect(), opening=opening)


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
            await pilot.click("#roll")
            await until(pilot, lambda: texts(app, "narration") == ["You creep.", "You slip past."]
                        and not isinstance(app.screen, RollScreen))
            assert texts(app, "roll") == ["Stealth: rolled 14 +1 = 15 against 12, success"]
            kinds = [e.kind for e in app.story.entries() if e.kind != "player"]
            assert kinds == ["narration", "roll", "narration"]
    run(scenario)


def test_the_roll_line_names_a_failure():
    from aimaginarium.api import RollResult
    assert roll_line(RollResult("climb", 3, 1, 4, 10)).endswith("against 10, failure")


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
