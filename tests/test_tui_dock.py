"""Tests for the dev dock's placement (#92): right or bottom, keeping the tab, the records and the sizes."""

import pytest

pytest.importorskip("textual")

from textual.widgets import TabbedContent  # noqa: E402
from textual_widgets import HorizontalSplitter, VerticalSplitter  # noqa: E402

from aimaginarium.api import Role  # noqa: E402
from aimaginarium.ui.tui.panels.trace import TraceTimeline  # noqa: E402
from aimaginarium.ui.tui.party import PartyBar  # noqa: E402
from engine_helpers import reply  # noqa: E402
from test_tui import act, instant, make_app, run, until  # noqa: E402,F401  (instant is an autouse fixture)


def parts(app):
    return app.query_one("#main"), app.query_one("#dev-dock"), app.query_one("#dock-splitter")


async def drag(pilot, splitter, dx=0, dy=0):
    """Drags a splitter by (dx, dy); it is one cell thick, so the grab point is on its own line or column."""
    x, y = (splitter.region.x + 5, splitter.region.y) if isinstance(splitter, HorizontalSplitter) \
        else (splitter.region.x, splitter.region.y + 3)
    await pilot.mouse_down(None, offset=(x, y))
    await pilot.hover(None, offset=(x + dx, y + dy))
    await pilot.mouse_up(None, offset=(x + dx, y + dy))
    await pilot.pause()


def test_the_dock_starts_on_the_right_and_moves_to_the_bottom_across_the_whole_width():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            main, dock, splitter = parts(app)
            assert dock.region.x >= main.region.right and isinstance(splitter, VerticalSplitter)
            await app.set_dock_placement("bottom")
            await pilot.pause(0.2)
            main, dock, splitter = parts(app)
            assert isinstance(splitter, HorizontalSplitter) and splitter.display
            assert dock.region.y >= main.region.bottom and dock.region.width == app.size.width   # under everything
            assert dock.region.width == main.region.width
            await app.set_dock_placement("right")
            await pilot.pause(0.2)
            main, dock, splitter = parts(app)
            assert dock.region.x >= main.region.right and isinstance(splitter, VerticalSplitter)
    run(scenario)


def test_moving_the_dock_keeps_the_tab_the_panels_and_what_they_recorded():
    async def scenario():
        app = make_app([reply(["Marta smiles."])], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "I greet Marta.")
            timeline = app.query_one(TraceTimeline)
            await until(pilot, lambda: timeline.records)
            tabs = app.query_one(TabbedContent)
            tabs.active = "tab-diffpanel"
            await pilot.pause(0.2)
            records = dict(timeline.records)
            await app.set_dock_placement("bottom")
            await pilot.pause(0.2)
            assert app.query_one(TraceTimeline) is timeline and timeline.records == records     # not rebuilt
            assert app.query_one(TabbedContent).active == "tab-diffpanel"
    run(scenario)


def test_each_placement_remembers_the_size_it_was_dragged_to():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            main, dock, splitter = parts(app)
            await drag(pilot, splitter, dx=-14)                                   # dock wider: the play area narrower
            wide = main.outer_size.width
            await app.set_dock_placement("bottom")
            await pilot.pause(0.2)
            main, dock, splitter = parts(app)
            default_height = main.outer_size.height
            await drag(pilot, splitter, dy=-6)                                    # dock taller
            tall = main.outer_size.height
            assert tall == default_height - 6
            await app.set_dock_placement("right")
            await pilot.pause(0.2)
            assert app.query_one("#main").outer_size.width == wide                # the width came back
            assert app.query_one("#main").outer_size.height == app.query_one("#workspace").outer_size.height
            await app.set_dock_placement("bottom")
            await pilot.pause(0.2)
            assert app.query_one("#main").outer_size.height == tall               # and so did the height
    run(scenario)


def test_hiding_the_bottom_dock_gives_the_play_area_the_whole_height_and_showing_it_restores_the_drag():
    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await app.set_dock_placement("bottom")
            await pilot.pause(0.2)
            main, dock, splitter = parts(app)
            await drag(pilot, splitter, dy=-5)
            dragged = main.outer_size.height
            await pilot.press("f2")
            await pilot.pause(0.2)
            workspace = app.query_one("#workspace")
            assert not dock.display and not splitter.display
            assert main.outer_size.height == workspace.outer_size.height
            await pilot.press("f2")
            await pilot.pause(0.2)
            assert dock.display and splitter.display and main.outer_size.height == dragged
    run(scenario)


def test_the_party_bar_on_the_right_stays_at_the_far_right_with_the_dock_beside_and_above_the_dock_below():
    async def scenario():
        app = make_app([], role=Role.DEV)
        app.settings.party_placement = "right"
        async with app.run_test(size=(160, 44)) as pilot:
            app.set_demo_party(3)
            bar = app.query_one(PartyBar)
            await until(pilot, lambda: len(bar.cards()) == 3)
            await pilot.pause(0.3)
            assert bar.region.x > app.query_one("#dev-dock").region.x                # past the dock, as before
            await app.set_dock_placement("bottom")
            await pilot.pause(0.3)
            bar = app.query_one(PartyBar)
            assert len(bar.cards()) == 3 and bar.parent.id == "main"
            assert bar.region.bottom <= app.query_one("#dev-dock").region.y          # above the dock, beside the story
            assert bar.region.x > app.query_one("#story-column").region.x
            await app.set_dock_placement("right")
            await pilot.pause(0.3)
            assert app.query_one(PartyBar).parent.id == "workspace" and len(app.query_one(PartyBar).cards()) == 3
    run(scenario)


def test_the_dock_command_and_the_palette_entry_move_it_and_a_player_has_neither():
    from aimaginarium.ui.tui.commands import DevCommands
    from aimaginarium.ui.tui.inputs import ActionInput

    async def scenario():
        app = make_app([], role=Role.DEV)
        async with app.run_test(size=(160, 44)) as pilot:
            await act(pilot, "/dock bottom")
            await until(pilot, lambda: app.settings.dock_placement == "bottom")
            await act(pilot, "/dock sideways")
            await until(pilot, lambda: any("Usage: /dock" in e.text for e in app.story.entries("system")))
            assert app.settings.dock_placement == "bottom"
            await act(pilot, "/dock")                                             # no argument: the other side
            await until(pilot, lambda: app.settings.dock_placement == "right")
            names = [name for name, *_ in DevCommands(app.screen)._entries()]
            assert "Move dev panels to the bottom" in names
    run(scenario)

    async def player():
        app = make_app([], role=Role.PLAYER)
        async with app.run_test(size=(160, 44)) as pilot:
            await app.set_dock_placement("bottom")                                # nothing to move
            assert app.settings.dock_placement == "right" and not app.query("#dev-dock")
            await act(pilot, "/dock bottom")
            await pilot.pause(0.2)
            assert any("Unknown command" in e.text for e in app.story.entries("system"))
            assert not DevCommands(app.screen)._entries()
    run(player)

    with pytest.raises(ValueError):
        async def bad():
            app = make_app([], role=Role.DEV)
            async with app.run_test(size=(160, 44)):
                await app.set_dock_placement("left")
        run(bad)
