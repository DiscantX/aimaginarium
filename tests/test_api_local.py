"""Tests for the in-process server: turns, the roll command, roles, subscription."""

import asyncio
import json

import pytest

from aimaginarium.api import (
    ChangesRejected, CheckCalled, CommandRejected, Done, GetPlayerView, GetState, GetTrace, LocalServer, Narration,
    OpenScene, Quit, Role, RoleError, Roll, RollResult, Server, Session, StateChanged, StateView, SubmitAction, Undo,
)
from aimaginarium.engine import PLAYER_ID, create_demo_world
from aimaginarium.world import WorldStore
from engine_helpers import make_game, reply, stealth_check


def served(replies, die=14, dev=True):
    store = WorldStore.open()
    create_demo_world(store)
    game, _ = make_game(store, replies, die)
    return LocalServer(game, dev_enabled=dev)


async def events(stream):
    return [e async for e in stream]


def run(coro):
    return asyncio.run(coro)


def kinds(envelopes):
    """Event type names, with a run of streamed narration chunks counted once."""
    names = [type(e.event).__name__ for e in envelopes]
    return [n for i, n in enumerate(names) if not (n == "Narration" and i and names[i - 1] == "Narration")]


def of(envelopes, cls):
    return next(e for e in envelopes if isinstance(e.event, cls))


def test_server_and_session_satisfy_the_protocols():
    server = served([])
    assert isinstance(server, Server) and isinstance(server.connect(), Session)


def test_dev_role_is_refused_when_disabled_and_player_cannot_send_dev_commands():
    with pytest.raises(RoleError):
        served([], dev=False).connect(Role.DEV)
    session = served([]).connect(Role.PLAYER)
    for command in (Undo(), GetState(), GetTrace()):
        with pytest.raises(RoleError):  # raised by send(), not later while reading the stream
            session.send(command)


def test_plain_turn_streams_narration_commits_and_ends_with_done():
    changes = [{"op": "update", "entity": PLAYER_ID, "set": {"sheet.mood": "calm"}}]
    session = served([reply(["Marta nods."], changes)], dev=False).connect()
    out = run(events(session.send(SubmitAction("I greet Marta."))))
    assert kinds(out) == ["Narration", "StateChanged", "Done"]
    assert [e.seq for e in out] == list(range(1, len(out) + 1)) and {e.turn_id for e in out} == {1}
    assert out[-1].event == Done(1, False)
    assert of(out, StateChanged).event.changes == ()  # raw changes are for the dev role only


def test_dev_role_receives_the_raw_changes():
    changes = [{"op": "update", "entity": PLAYER_ID, "set": {"sheet.mood": "calm"}}]
    session = served([reply(["Marta nods."], changes)]).connect(Role.DEV)
    out = run(events(session.send(SubmitAction("I greet Marta."))))
    assert of(out, StateChanged).event.changes[0]["kind"] == "entity.updated"


def test_a_check_turn_pauses_until_roll_and_hides_the_gms_workings_from_players():
    server = served([reply(["You creep."], check=stealth_check("The guard is a spy.")), reply(["You slip past."])])
    player = server.connect()

    async def scenario():
        first = await events(player.send(SubmitAction("I sneak.")))
        assert kinds(first) == ["Narration", "CheckCalled", "Done"]
        assert first[-1].event == Done(1, True)
        called = of(first, CheckCalled).event
        assert (called.skill, called.difficulty, called.reason, called.workings) == ("stealth", 12, "", None)
        assert "roll" not in [e.kind for e in server.game.store.events()]
        second = await events(player.send(Roll()))
        assert kinds(second) == ["RollResult", "Narration", "Done"]
        assert second[0].event == RollResult("stealth", 14, 1, 15, 12) and second[-1].event == Done(1, False)

    run(scenario())
    log = server._log
    secret = next(e.for_role(Role.DEV).event for e in log if isinstance(e.event, CheckCalled))
    assert secret.reason == "The guard is a spy." and secret.workings["tier"] == "easy" and secret.workings["difficulty"] == 12


def test_commands_at_the_wrong_moment_are_rejected_with_done():
    session = served([reply(["You creep."], check=stealth_check()), reply(["You slip past."])]).connect()

    async def scenario():
        early = await events(session.send(Roll()))
        await events(session.send(SubmitAction("I sneak.")))
        busy = await events(session.send(SubmitAction("I look.")))
        return early, busy

    early, busy = run(scenario())
    assert [e.event.code for e in early if isinstance(e.event, CommandRejected)] == ["not_awaiting_roll"]
    assert [e.event.code for e in busy if isinstance(e.event, CommandRejected)] == ["awaiting_roll"]
    assert isinstance(early[-1].event, Done) and isinstance(busy[-1].event, Done)


def test_the_scene_can_only_be_opened_once():
    session = served([reply(["The story begins."])]).connect()
    run(events(session.send(OpenScene())))
    again = run(events(session.send(OpenScene())))
    assert again[0].event.code == "already_begun"


def test_rejected_changes_give_players_no_error_detail():
    bad = [{"op": "move", "entity": "item-99", "to": PLAYER_ID}]
    player = served([reply(["Done."], bad), '{"changes": []}']).connect()
    out = run(events(player.send(SubmitAction("I take it."))))
    rejected = next(e.event for e in out if isinstance(e.event, ChangesRejected))
    assert rejected.errors == ()


def test_player_view_has_no_ids_and_gm_view_is_dev_only():
    server = served([])
    view = run(events(server.connect().send(GetPlayerView())))[0].event
    assert isinstance(view, StateView) and view.perspective == "player"
    assert "char-2" not in json.dumps(view.data) and view.data["story"] == []
    gm = run(events(server.connect(Role.DEV).send(GetState())))[0].event
    assert gm.perspective == "gm" and "Marta [char-2]" in gm.data["world_state"]


def test_unbuilt_dev_commands_are_rejected_politely():
    dev = served([]).connect(Role.DEV)
    out = run(events(dev.send(Undo())))
    assert out[0].event.code == "not_available" and isinstance(out[-1].event, Done)


def test_subscribers_replay_and_follow_the_log_until_the_session_closes():
    server = served([reply(["One."]), reply(["Two."])], dev=False)
    player, watcher = server.connect(), server.connect()

    async def scenario():
        await events(player.send(SubmitAction("first")))
        seen = []

        async def follow():
            async for envelope in watcher.subscribe(since=0):
                seen.append(envelope)

        task = asyncio.create_task(follow())
        await asyncio.sleep(0)
        await events(player.send(SubmitAction("second")))
        await asyncio.sleep(0)
        await watcher.close()
        await asyncio.wait_for(task, 1)
        return seen

    seen = run(scenario())
    assert [e.seq for e in seen] == list(range(1, len(seen) + 1)) and kinds(seen) == ["Narration", "Done"] * 2
    assert [e.event.text for e in seen if isinstance(e.event, Narration)] == ["One.", "Two."]


def test_quit_closes_the_session():
    session = served([]).connect()
    out = run(events(session.send(Quit())))
    assert isinstance(out[-1].event, Done)
    with pytest.raises(RuntimeError):
        session.send(GetPlayerView())
