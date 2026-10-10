"""The dev-note command in the Textual client."""

import pytest

pytest.importorskip("textual")

from aimaginarium.api import Role  # noqa: E402
from aimaginarium.devstore import DevStore  # noqa: E402
from engine_helpers import reply  # noqa: E402
from test_tui import act, instant, make_app, run, texts, until  # noqa: E402,F401  (instant is an autouse fixture)


def test_dn_and_dev_note_attach_notes_and_say_so_in_the_story():
    async def scenario():
        with DevStore.open() as dev:
            app = make_app([reply(["Marta nods."])], role=Role.DEV, devstore=dev)
            async with app.run_test(size=(140, 40)) as pilot:
                await act(pilot, "/dn too early")
                await until(pilot, lambda: any("no turn yet" in t for t in texts(app, "system")))
                await act(pilot, "I greet Marta.")
                await until(pilot, lambda: texts(app, "narration"))
                await act(pilot, "/dn #tone Marta is too curt")
                await until(pilot, lambda: any("Dev note 1 added to turn 1." in t for t in texts(app, "system")))
                await act(pilot, "/dev-note 1 #rules and again")
                await until(pilot, lambda: any("Dev note 2 added to turn 1." in t for t in texts(app, "system")))
                await act(pilot, "/dn")
                await until(pilot, lambda: any("Usage: /dn" in t for t in texts(app, "system")))
                world_id = app.session._server.game.store.world_id
                assert [(n.text, n.tags) for n in dev.notes(world_id)] == [
                    ("Marta is too curt", ("tone",)), ("and again", ("rules",))]
    run(scenario)


def test_a_player_has_no_dn_command_and_nothing_is_stored():
    async def scenario():
        with DevStore.open() as dev:
            app = make_app([], role=Role.PLAYER, devstore=dev)
            async with app.run_test(size=(140, 40)) as pilot:
                await act(pilot, "/dn hello")
                await until(pilot, lambda: any("Unknown command /dn" in t for t in texts(app, "system")))
                assert dev.notes(app.session._server.game.store.world_id) == []
    run(scenario)
