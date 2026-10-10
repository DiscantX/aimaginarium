"""Tests for the character panel, driven by Textual's pilot."""

import pytest

pytest.importorskip("textual")

from aimaginarium.api import Role  # noqa: E402
from aimaginarium.ui.tui.character import CharacterPanel  # noqa: E402
from aimaginarium.ui.tui.party import PartyBar  # noqa: E402
from test_tui import act, instant, make_app, run, until  # noqa: E402,F401  (instant is an autouse fixture)


def panel(app):
    return app.query_one(CharacterPanel)


def shown(app, key):
    return app.query_one(f"#cp-sec-{key}").display


def test_the_panel_shows_the_players_own_character_from_the_start_for_any_role():
    async def scenario():
        for role in (Role.PLAYER, Role.DEV):
            app = make_app([], role=role)
            async with app.run_test(size=(120, 40)) as pilot:
                await until(pilot, lambda: panel(app).view is not None)
                view = panel(app).view
                assert (view.name, view.class_name, view.ac, view.mine) == ("Kael", "Fighter", 16, True)
                assert view.abilities["str"] == 16 and [i.name for i in view.inventory] == ["Shortsword", "Coin purse"]
                assert not app.query_one("#cp-viewing").display  # your own character needs no note
    run(scenario)


def test_sections_without_anything_in_them_are_left_out_and_the_rest_have_counts():
    async def scenario():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await until(pilot, lambda: panel(app).view is not None)
            assert shown(app, "skills") and shown(app, "inventory") and shown(app, "features") and shown(app, "about")
            assert not shown(app, "spells") and not shown(app, "equipment") and not shown(app, "conditions")
            assert app.query_one("#cp-sec-inventory").title == "Inventory (2)"
    run(scenario)


def test_selecting_another_member_shows_that_character_and_says_so():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 40)) as pilot:
            app.set_demo_party(3)
            await until(pilot, lambda: len(app.query_one(PartyBar).cards()) == 3)
            await pilot.press("f4", "right")
            await until(pilot, lambda: panel(app).view.name == "Mira Vael")
            assert not panel(app).view.mine and app.query_one("#cp-viewing").display
            assert shown(app, "spells") and shown(app, "equipment")  # stand-in members have full sheets
            await pilot.press("escape")
            await until(pilot, lambda: panel(app).view.name == "Kael")
            assert not app.query_one("#cp-viewing").display
    run(scenario)


def test_a_member_the_api_says_little_about_shows_little_and_says_so():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(120, 40)) as pilot:
            app.set_demo_party(2)
            await until(pilot, lambda: len(app.query_one(PartyBar).cards()) == 2)
            app.characters.pop("demo-0")  # as if the projection held nothing but the card
            await pilot.press("f4", "right")
            await until(pilot, lambda: panel(app).view.name == "Mira Vael")
            assert panel(app).view.abilities == {} and not shown(app, "skills") and not shown(app, "spells")
    run(scenario)


def test_f5_hides_and_shows_the_panel_with_its_splitter():
    async def scenario():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            assert panel(app).display and app.query_one("#character-splitter").display
            await pilot.press("f5")
            assert not panel(app).display and not app.query_one("#character-splitter").display
            await pilot.press("f5")
            assert panel(app).display
    run(scenario)


def test_the_panel_reads_the_sheet_again_when_the_world_changes_and_can_show_nothing():
    from aimaginarium.engine import create_demo_world
    from aimaginarium.world import Update, WorldStore
    from test_tui import GameApp, LocalServer, make_game

    async def scenario():
        store = WorldStore.open()
        player_id = create_demo_world(store)
        app = GameApp(LocalServer(make_game(store, [], 15)[0], dev_enabled=True).connect(Role.PLAYER), opening=False)
        app.animation_level = "none"
        async with app.run_test(size=(120, 40)) as pilot:
            await until(pilot, lambda: panel(app).view is not None)
            assert panel(app).view.hp == 24
            store.commit([Update(entity=player_id, set={"sheet.hp": 10, "sheet.statuses": ["poisoned"]})], actor="system")
            await app._load_party()  # what a StateChanged event triggers
            assert panel(app).view.hp == 10 and shown(app, "conditions")
            panel(app).show(None)
            assert panel(app).view.name == ""
    run(scenario)


def test_the_panel_can_be_resized_by_dragging_its_splitter():
    async def scenario():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            before = panel(app).outer_size.width
            splitter = app.query_one("#character-splitter")
            await pilot.mouse_down(splitter, offset=(0, 10))
            await pilot.hover("#story-column", offset=(5, 10))
            await pilot.mouse_up("#story-column", offset=(5, 10))
            await pilot.pause(0.2)
            assert panel(app).outer_size.width > before
    run(scenario)
