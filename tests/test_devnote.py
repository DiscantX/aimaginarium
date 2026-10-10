"""Tests for dev notes through the API, the command line and the clients."""

import argparse
import asyncio

import pytest

from aimaginarium.api import (
    AddDevNote, DevNoteAdded, DevNoteList, GetDevNotes, GetTrace, LocalServer, Role, RoleError,
    SubmitAction, TraceEvent, Undo, parse_command,
)
from aimaginarium.devstore import DevStore
from aimaginarium.engine import create_demo_world
from aimaginarium.ui import devnote
from aimaginarium.world import WorldStore
from engine_helpers import make_game, reply

NOTE_TEXT = "DEVNOTE-MARKER the cellar moved"


def served(replies, devstore=True, dev=True):
    store = WorldStore.open()
    create_demo_world(store)
    game, provider = make_game(store, replies)
    dev_store = DevStore.open() if devstore else None
    if dev_store is not None:
        game.tracer.add_sink(dev_store.trace_sink(store.world_id))
    return LocalServer(game, dev_enabled=dev, devstore=dev_store), provider


async def send(session, command):
    return [e.event async for e in session.send(command)]


def run(coro):
    return asyncio.run(coro)


# -- the command line -------------------------------------------------------

def test_the_command_line_gives_a_turn_tags_and_text():
    assert devnote.parse("the cellar moved") == devnote.ParsedNote(None, (), "the cellar moved")
    assert devnote.parse("12 the cellar moved") == devnote.ParsedNote(12, (), "the cellar moved")
    parsed = devnote.parse("#Continuity   the cellar #world moved #continuity")
    assert parsed == devnote.ParsedNote(None, ("continuity", "world"), "the cellar moved")
    assert devnote.parse("see #12 for why").text == "see #12 for why"          # a number after # is not a tag


@pytest.mark.parametrize("args", ["", "   ", "12", "#tone", "3 #tone #more"])
def test_a_command_line_without_text_is_refused_with_the_usage(args):
    with pytest.raises(ValueError, match="Usage: /dn"):
        devnote.parse(args)


def test_the_command_answers_to_both_names_and_never_to_note():
    assert devnote.COMMANDS == ("/dn", "/dev-note") and "/note" not in devnote.COMMANDS


# -- the API -----------------------------------------------------------------

def test_the_commands_travel_in_wire_form_and_are_dev_only():
    command = AddDevNote("x", 3, ("a", "b"), {"trace_seq": 2}, "q")
    assert parse_command(command.to_dict()) == command
    assert parse_command({"command": "add_dev_note", "text": "x", "tags": ["a"]}).tags == ("a",)   # JSON gives a list
    for bad in ({"command": "add_dev_note", "text": " "}, {"command": "get_dev_notes", "status": "done"},
                {"command": "get_trace", "around": -1}):
        with pytest.raises(ValueError):
            parse_command(bad)
    for command in (AddDevNote("x"), GetDevNotes()):
        with pytest.raises(RoleError):
            command.check(Role.PLAYER)
    assert DevNoteAdded.roles == DevNoteList.roles == frozenset({Role.DEV})


def test_a_note_goes_to_the_latest_turn_by_default_and_quotes_it():
    async def scenario():
        server, _ = served([reply(["Marta smiles and pours you an ale."])])
        dev = server.connect(Role.DEV)
        await send(dev, SubmitAction("I greet Marta."))
        added = (await send(dev, AddDevNote("The ale was free?", tags=("rules",))))[0]
        note = added.note
        assert isinstance(added, DevNoteAdded) and note["turn_id"] == 1 and note["tags"] == ["rules"]
        assert note["excerpt"] == "> I greet Marta. Marta smiles and pours you an ale."
        explicit = (await send(dev, AddDevNote("again", turn=1, excerpt="my selection")))[0].note
        assert explicit["excerpt"] == "my selection"
        listed = (await send(dev, GetDevNotes()))[0]
        assert isinstance(listed, DevNoteList) and [n["id"] for n in listed.notes] == [note["id"], explicit["id"]]
        assert (await send(dev, GetDevNotes(tag="rules")))[0].notes[0]["id"] == note["id"]
        assert (await send(dev, GetDevNotes(status="resolved")))[0].notes == ()
    run(scenario())


def test_a_note_is_refused_without_a_turn_for_an_unknown_turn_or_without_a_store():
    async def scenario():
        server, _ = served([reply(["Hi."])])
        dev = server.connect(Role.DEV)
        assert (await send(dev, AddDevNote("x")))[0].code == "no_turn"
        await send(dev, SubmitAction("hello"))
        assert (await send(dev, AddDevNote("x", turn=9)))[0].code == "unknown_turn"
        bare, _ = served([reply(["Hi."])], devstore=False)
        session = bare.connect(Role.DEV)
        await send(session, SubmitAction("hello"))
        assert (await send(session, AddDevNote("x")))[0].code == "not_available"
        assert (await send(session, GetDevNotes()))[0].code == "not_available"
    run(scenario())


def test_a_turn_that_was_taken_back_can_still_be_noted():
    async def scenario():
        server, _ = served([reply(["The cellar is behind the tavern."])])
        dev = server.connect(Role.DEV)
        await send(dev, SubmitAction("I look for the cellar."))
        await send(dev, Undo())
        added = (await send(dev, AddDevNote("This turn was wrong.", turn=1)))[0]
        assert isinstance(added, DevNoteAdded) and "cellar" in added.note["excerpt"]     # ids are never reused
    run(scenario())


def test_a_dev_note_never_reaches_an_llm_prompt_or_the_world_state():
    async def scenario():
        server, provider = served([reply(["One."]), reply(["Two."])])
        dev = server.connect(Role.DEV)
        await send(dev, SubmitAction("first"))
        await send(dev, AddDevNote(NOTE_TEXT, tags=("continuity",)))
        await send(dev, SubmitAction("second"))
        sent = " ".join(str(r) for r in provider.requests)
        assert NOTE_TEXT not in sent and "continuity" not in sent
        store = server.game.store
        assert NOTE_TEXT not in " ".join(str(e.payload) for e in store.events(include_retracted=True))
        assert not store.connection.execute("SELECT 1 FROM sqlite_master WHERE name LIKE '%note%'").fetchall()
    run(scenario())


def test_the_player_role_never_sees_dev_notes():
    async def scenario():
        server, _ = served([reply(["Hi."])])
        dev, player = server.connect(Role.DEV), server.connect(Role.PLAYER)
        await send(dev, SubmitAction("hello"))
        await send(dev, AddDevNote(NOTE_TEXT))
        seen = await _first(player.subscribe(), 50)
        assert not any(isinstance(e.event, DevNoteAdded) for e in seen)
        assert NOTE_TEXT not in str([e.to_dict() for e in seen])
    run(scenario())


async def _first(stream, count):
    """Up to ``count`` envelopes already in the log, without waiting for more."""
    items = []

    async def collect():
        async for item in stream:
            items.append(item)
            if len(items) >= count:
                break

    try:
        await asyncio.wait_for(collect(), 0.2)
    except asyncio.TimeoutError:
        pass
    return items


# -- the trace of a turn and its neighbours -----------------------------------

def test_a_turn_and_the_turns_around_it_come_from_the_dev_store_even_after_a_restart():
    async def scenario():
        server, _ = served([reply([f"Turn {n}."]) for n in (1, 2, 3, 4)])
        dev = server.connect(Role.DEV)
        for n in (1, 2, 3, 4):
            await send(dev, SubmitAction(f"action {n}"))
        turns = lambda events: sorted({e.turn_id for e in events if isinstance(e, TraceEvent)})  # noqa: E731
        assert turns(await send(dev, GetTrace(turn=3))) == [3]
        assert turns(await send(dev, GetTrace(turn=3, around=1))) == [2, 3, 4]
        restarted = LocalServer(server.game, dev_enabled=True, devstore=server.devstore)
        restarted.game.tracer._buffer.clear()                         # a new run: nothing in memory
        again = restarted.connect(Role.DEV)
        assert turns(await send(again, GetTrace(turn=2, around=1))) == [1, 2, 3]
        prompts = [e for e in await send(again, GetTrace(turn=2)) if isinstance(e, TraceEvent) and e.kind == "llm.call"]
        assert "action 2" in str(prompts[0].payload["messages"])      # the full prompt is there
    run(scenario())


def test_without_a_dev_store_a_turn_comes_from_the_in_memory_trace_with_its_neighbours():
    async def scenario():
        server, _ = served([reply(["A."]), reply(["B."]), reply(["C."])], devstore=False)
        dev = server.connect(Role.DEV)
        for n in (1, 2, 3):
            await send(dev, SubmitAction(f"action {n}"))
        got = {e.turn_id for e in await send(dev, GetTrace(turn=2, around=1)) if isinstance(e, TraceEvent)}
        assert got == {1, 2, 3}
    run(scenario())


# -- startup -------------------------------------------------------------------

def test_the_dev_role_gets_a_dev_store_beside_the_world_and_keeps_the_trace_in_it(tmp_path, monkeypatch):
    from aimaginarium.llm import Capabilities, ProviderFactory
    from aimaginarium.llm.providers.fake import FakeProvider
    from aimaginarium.ui import bootstrap

    def factory(*args, **kwargs):
        provider = FakeProvider([], capabilities=Capabilities(schema_enforcement=True))
        return ProviderFactory({"providers": {"f": {"kind": "fake", "model": "m"}}, "tasks": {"default": {"provider": "f"}}},
                               env={}, builders={"fake": lambda spec, env: provider})

    monkeypatch.setattr(bootstrap, "factory_from_file", factory)
    parser = argparse.ArgumentParser()
    bootstrap.add_common_arguments(parser)

    world = tmp_path / "worlds" / "w.sqlite"
    runtime = bootstrap.Runtime.open(parser.parse_args(["--world", str(world), "--dev"]))
    runtime._tracer.emit("llm.call", {"x": 1}, turn=1)
    runtime.close()
    assert (tmp_path / "worlds" / "dev.sqlite").exists()
    with WorldStore.open(world) as store, DevStore.open(tmp_path / "worlds" / "dev.sqlite") as dev:
        assert [r.payload for r in dev.trace(store.world_id, 1)] == [{"x": 1}]

    plain = tmp_path / "plain"
    runtime = bootstrap.Runtime.open(parser.parse_args(["--world", str(plain / "w.sqlite")]))
    runtime.close()
    assert not (plain / "dev.sqlite").exists()                              # no dev role, no dev store

    custom = tmp_path / "mine" / "notes.sqlite"
    runtime = bootstrap.Runtime.open(parser.parse_args(["--world", str(plain / "w.sqlite"), "--dev", "--dev-store", str(custom)]))
    runtime.close()
    assert custom.exists()
