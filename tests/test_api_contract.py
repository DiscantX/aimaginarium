"""Tests for the internal API contract (#56): commands, events, roles."""

import dataclasses
import json

import pytest

from aimaginarium.api import (
    ApiEvent, ChangesRejected, CheckCalled, Command, Done, Envelope, GetState, GetTrace, InputPath, Narration,
    OpenScene, Quit, Role, RoleError, Roll, RollResult, Server, Session, StateChanged, StateView, SubmitAction,
    TraceEvent, Undo, parse_command,
)
from aimaginarium.api import commands as commands_module
from aimaginarium.api import events as events_module


def all_commands():
    return list(commands_module._REGISTRY.values())


def all_events():
    return [c for c in vars(events_module).values()
            if isinstance(c, type) and issubclass(c, ApiEvent) and c is not ApiEvent]


def test_player_path_has_no_in_game_verbs():
    player_path = {c.name for c in all_commands() if c.path is InputPath.PLAYER}
    assert player_path == {"open_scene", "submit_action", "roll"}


def test_dev_commands_are_refused_for_the_player_role():
    for cmd in (Undo(), GetState(), GetTrace()):
        with pytest.raises(RoleError):
            cmd.check(Role.PLAYER)
        cmd.check(Role.DEV)


def test_player_commands_are_allowed_for_both_roles():
    for cmd in (OpenScene(), SubmitAction("look"), Roll(), Quit()):
        cmd.check(Role.PLAYER)
        cmd.check(Role.DEV)


def test_commands_round_trip_through_the_wire_form():
    for cmd in (OpenScene(), SubmitAction("I open the door"), Roll(), Quit(), Undo(), GetState("player"), GetTrace(5, 10)):
        assert parse_command(json.loads(json.dumps(cmd.to_dict()))) == cmd


@pytest.mark.parametrize("data", [
    {}, {"command": "attack"}, {"command": "submit_action"}, {"command": "submit_action", "text": "  "},
    {"command": "roll", "extra": 1}, {"command": "get_state", "perspective": "dm"}, {"command": "get_trace", "limit": 0},
])
def test_bad_commands_are_rejected(data):
    with pytest.raises(ValueError):
        parse_command(data)


def test_every_command_and_event_has_a_unique_wire_name():
    assert len({c.name for c in all_commands()}) == len(all_commands())
    assert len({e.name for e in all_events()}) == len(all_events())


def test_player_never_receives_dev_only_fields():
    called = CheckCalled("stealth", 12, reason="the guard is a spy", workings={"tier": "easy"})
    seen = called.for_role(Role.PLAYER)
    assert (seen.skill, seen.difficulty) == ("stealth", 12)
    assert seen.reason == "" and seen.workings is None
    assert called.for_role(Role.DEV) is called

    rejected = ChangesRejected(errors=("no such entity 'secret_door'",))
    assert rejected.for_role(Role.PLAYER).errors == ()
    changed = StateChanged(changes=({"kind": "entity.move"},))
    assert changed.for_role(Role.PLAYER).changes == ()


def test_every_dev_only_field_is_stripped_for_players():
    for cls in all_events():
        for f in dataclasses.fields(cls):
            if f.metadata.get("dev_only"):
                assert f.default is not dataclasses.MISSING, f"{cls.__name__}.{f.name} needs a default to fall back to"


def test_trace_events_are_dev_only():
    trace = TraceEvent("llm.call", {"task": "narrate"})
    assert trace.for_role(Role.PLAYER) is None
    assert trace.for_role(Role.DEV) is trace


def test_gm_state_view_is_dev_only_but_player_view_is_not():
    assert StateView("gm", {"x": 1}).for_role(Role.PLAYER) is None
    assert StateView("gm", {"x": 1}).for_role(Role.DEV) is not None
    view = StateView("player", {"x": 1})
    assert view.for_role(Role.PLAYER) is view


def test_envelope_filters_by_role_and_serialises():
    env = Envelope(3, 7, CheckCalled("stealth", 12, reason="secret"))
    assert env.for_role(Role.PLAYER).event.reason == ""
    assert Envelope(4, 7, TraceEvent("k", {})).for_role(Role.PLAYER) is None
    wire = json.loads(json.dumps(env.for_role(Role.PLAYER).to_dict()))
    assert wire == {"seq": 3, "turn_id": 7, "event": {
        "type": "check_called", "skill": "stealth", "difficulty": 12, "reason": "", "workings": None}}


def test_done_marks_a_paused_turn():
    assert Done(turn_id=2, awaiting_roll=True).to_dict() == {"type": "done", "turn_id": 2, "awaiting_roll": True}
    assert Done().awaiting_roll is False


def test_roll_result_carries_the_visible_numbers():
    assert {f.name for f in dataclasses.fields(RollResult)} == {"skill", "die", "modifier", "total", "difficulty"}


def test_protocols_are_importable_and_runtime_checkable():
    class Fake:
        role = Role.PLAYER

        def send(self, command):
            ...

        def subscribe(self, since=0):
            ...

        async def close(self):
            ...

    assert isinstance(Fake(), Session)
    assert not isinstance(object(), Server)
    assert issubclass(SubmitAction, Command)
    assert isinstance(Narration("x"), ApiEvent)
