"""Tests for the party bar, driven by Textual's pilot."""

import pytest

pytest.importorskip("textual")

from aimaginarium.api import Role  # noqa: E402
from aimaginarium.ui.party import PartyMember  # noqa: E402
from aimaginarium.ui.tui.inputs import ActionInput  # noqa: E402
from aimaginarium.ui.tui.party import PartyBar, PartyCard, hp_bar  # noqa: E402
from test_tui import act, instant, make_app, run, until  # noqa: E402,F401  (instant is an autouse fixture)


def bar(app):
    return app.query_one(PartyBar)


def test_hp_bar_shows_unknown_full_and_never_empties_a_living_member():
    assert hp_bar(PartyMember("a", "A")) == "HP ?"
    assert hp_bar(PartyMember("a", "A", hp=20, max_hp=20)) == "20/20 " + "▓" * 10
    assert hp_bar(PartyMember("a", "A", hp=1, max_hp=100)) == "1/100 ▓" + "░" * 9
    assert hp_bar(PartyMember("a", "A", hp=0, max_hp=20)) == "0/20 " + "░" * 10


def test_the_bar_is_hidden_for_a_party_of_one_and_shown_when_the_setting_says_so():
    async def scenario():
        app = make_app([])
        async with app.run_test() as pilot:
            await until(pilot, lambda: bar(app).members)
            assert [m.name for m in app.party] == ["Kael"] and not bar(app).display
        app = make_app([])
        app.settings.party_always_show = True
        async with app.run_test() as pilot:
            await until(pilot, lambda: bar(app).members)
            assert bar(app).display
    run(scenario)


def test_a_stand_in_party_shows_cards_for_dev_and_is_unknown_to_players():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test() as pilot:
            await act(pilot, "/party 4")
            await until(pilot, lambda: len(bar(app).cards()) == 4)
            assert bar(app).display and bar(app).cards()[0].member.mine
            await act(pilot, "/party off")
            await until(pilot, lambda: len(bar(app).cards()) == 1)
            assert not bar(app).display
        player = make_app([])
        async with player.run_test() as pilot:
            await act(pilot, "/party 4")
            await until(pilot, lambda: any("Unknown command" in t for t in [e.text for e in player.story.entries("system")]))
            assert len(bar(player).cards()) == 1
    run(scenario)


def test_clicking_a_card_changes_the_viewed_member_but_not_the_players_own():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 36)) as pilot:
            app.set_demo_party(4)
            await until(pilot, lambda: len(bar(app).cards()) == 4)
            assert app.viewed.mine
            card = bar(app).cards()[2]
            await pilot.click(card)
            await until(pilot, lambda: not app.viewed.mine)
            assert app.viewed.id == card.member.id and bar(app).mine.name == "Kael"
            assert card.has_class("selected") and not bar(app).cards()[0].has_class("selected")
    run(scenario)


def test_keyboard_moves_the_selection_and_escape_returns_to_the_players_character():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 36)) as pilot:
            app.set_demo_party(3)
            await until(pilot, lambda: len(bar(app).cards()) == 3)
            await pilot.press("f3")
            assert bar(app).has_focus
            await pilot.press("right", "right", "right")  # clamped at the last member
            assert app.viewed.id == bar(app).members[-1].id
            await pilot.press("escape")
            assert app.viewed.mine and app.query_one(ActionInput).has_focus
            await pilot.press("f3", "right", "enter")
            assert not app.viewed.mine and app.query_one(ActionInput).has_focus  # enter keeps the selection
    run(scenario)


def test_the_selection_survives_a_refresh_of_the_same_party():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 36)) as pilot:
            app.set_demo_party(3)
            await until(pilot, lambda: len(bar(app).cards()) == 3)
            bar(app).select(bar(app).members[1].id)
            changed = [PartyMember(**{**m.__dict__, "hp": 1}) if m.id == bar(app).members[1].id else m for m in bar(app).members]
            await bar(app).set_party(changed)
            assert bar(app).selected.hp == 1 and bar(app).cards()[1].has_class("selected")
    run(scenario)


def test_the_bar_can_sit_on_the_right_and_an_unknown_placement_is_refused():
    async def scenario():
        app = make_app([], role=Role.DEV)
        app.settings.party_placement = "right"
        async with app.run_test(size=(120, 36)) as pilot:
            app.set_demo_party(3)
            await until(pilot, lambda: len(bar(app).cards()) == 3)
            assert bar(app).parent.id == "main" and bar(app).has_class("-right")
    run(scenario)
    with pytest.raises(ValueError):
        PartyBar("bottom")
