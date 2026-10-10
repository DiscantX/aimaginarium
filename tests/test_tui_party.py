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
            await pilot.press("f4")
            assert bar(app).has_focus
            await pilot.press("right", "right", "right")  # clamped at the last member
            assert app.viewed.id == bar(app).members[-1].id
            await pilot.press("escape")
            assert app.viewed.mine and app.query_one(ActionInput).has_focus
            await pilot.press("f4", "right", "enter")
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


def test_f3_toggles_the_bar_over_the_automatic_choice_and_showing_it_focuses_it():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 36)) as pilot:
            await until(pilot, lambda: bar(app).members)
            assert not bar(app).display  # a party of one is hidden
            await pilot.press("f3")
            assert bar(app).display and bar(app).has_focus  # shown on request, even for one member
            await pilot.press("f3")
            assert not bar(app).display and app.query_one(ActionInput).has_focus
            app.set_demo_party(3)
            await until(pilot, lambda: len(bar(app).cards()) == 3)
            assert not bar(app).display  # the player's choice to hide stays when the party grows
            await pilot.press("f3")
            assert bar(app).display
    run(scenario)


def test_the_bar_moves_between_top_and_right_keeping_the_party_and_selection():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 36)) as pilot:
            app.set_demo_party(4)
            await until(pilot, lambda: len(bar(app).cards()) == 4)
            bar(app).select(bar(app).members[2].id)
            await act(pilot, "/party right")
            await until(pilot, lambda: bar(app).has_class("-right"))
            assert bar(app).parent.id == "main" and len(bar(app).cards()) == 4 and bar(app).display
            assert bar(app).selected.id == app.viewed.id == bar(app).members[2].id
            assert app.settings.party_placement == "right"
            await app.action_move_party()  # the palette entry, open to every role
            assert bar(app).has_class("-top") and len(bar(app).cards()) == 4 and bar(app).selected.id == app.viewed.id
            assert list(app.screen.children).index(bar(app)) < list(app.screen.children).index(app.query_one("#main"))
    run(scenario)


def test_a_player_can_move_the_bar_and_a_stand_in_party_may_be_large():
    async def scenario():
        app = make_app([])
        async with app.run_test(size=(120, 36)) as pilot:
            await until(pilot, lambda: bar(app).members)
            await app.action_move_party()
            assert bar(app).has_class("-right")
        dev = make_app([], role=Role.DEV)
        async with dev.run_test(size=(120, 36)) as pilot:
            await act(pilot, "/party 30")
            await until(pilot, lambda: len(bar(dev).cards()) == 30)
    run(scenario)


def wheel(widget, kind, shift=False):
    """Posts a mouse wheel event over a widget."""
    from textual import events
    widget.post_message(kind(widget, 2, 2, 0, 1, 0, shift, False, False))


def test_the_wheel_scrolls_the_top_bar_sideways_and_the_column_vertically():
    from textual import events

    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(80, 36)) as pilot:
            app.set_demo_party(12)
            await until(pilot, lambda: len(bar(app).cards()) == 12)
            assert bar(app).scroll_x == 0
            wheel(bar(app), events.MouseScrollDown)
            await until(pilot, lambda: bar(app).scroll_x > 0)
            moved = bar(app).scroll_x
            wheel(bar(app), events.MouseScrollUp)
            await until(pilot, lambda: bar(app).scroll_x < moved)
            wheel(bar(app).cards()[1], events.MouseScrollDown)  # over a card: it bubbles to the bar
            await until(pilot, lambda: bar(app).scroll_x > 0)
            await app.set_party_placement("right")
            await pilot.pause(0.2)
            wheel(bar(app), events.MouseScrollDown)
            await until(pilot, lambda: bar(app).scroll_y > 0)
    run(scenario)
