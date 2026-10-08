"""Tests for the trace channel: tracer, sinks, engine tracing, the dev role's view and /inspect."""

import asyncio
import json

import pytest

from aimaginarium.api import GetTrace, LocalServer, Role, RoleError, SubmitAction, TraceEvent
from aimaginarium.cli import play
from aimaginarium.engine import PLAYER_ID, create_demo_world
from aimaginarium.llm import FallbackNotice, RetryNotice
from aimaginarium.trace import JsonlSink, Tracer, format_timeline
from aimaginarium.world import WorldStore
from engine_helpers import make_game, reply, stealth_check

BAD = [{"op": "move", "entity": "item-99", "to": PLAYER_ID}]
FIX = '{"changes": [{"op": "update", "entity": "%s", "set": {"sheet.x": 1}}]}' % PLAYER_ID


def traced_game(replies, die=14):
    store = WorldStore.open()
    create_demo_world(store)
    return make_game(store, replies, die)[0]


def run(coro):
    return asyncio.run(coro)


async def turn(game, text):
    return [e async for e in game.take_turn(PLAYER_ID, text)] + (
        [e async for e in game.resolve_check()] if game.awaiting_roll else [])


def test_records_are_numbered_filtered_and_bounded():
    tracer = Tracer(keep=3)
    tracer.turn = 1
    for i in range(5):
        tracer.emit("x", {"i": i}, turn=2 if i == 4 else None)
    assert [r.seq for r in tracer.records()] == [3, 4, 5]
    assert [r.seq for r in tracer.records(since=3)] == [4, 5]
    assert [r.seq for r in tracer.records(limit=1)] == [3]
    assert [r.seq for r in tracer.records(turn=2)] == [5] and tracer.records()[0].turn_id == 1


def test_a_failing_sink_is_dropped_and_never_breaks_tracing():
    tracer, seen = Tracer(), []

    def broken(record):
        raise OSError("disk full")

    tracer.add_sink(broken)
    tracer.add_sink(seen.append)
    tracer.emit("a")
    tracer.emit("b")
    assert [r.kind for r in seen] == ["a", "b"] and len(tracer._sinks) == 1


def test_file_sink_writes_one_json_line_per_record(tmp_path):
    path = tmp_path / "sub" / "trace.jsonl"
    tracer = Tracer()
    tracer.add_sink(JsonlSink(path))
    tracer.emit("llm.call", {"task": "narrate", "odd": {1, 2}}, turn=4)
    tracer.close()
    line = json.loads(path.read_text().strip())
    assert (line["seq"], line["turn"], line["kind"], line["payload"]["task"]) == (1, 4, "llm.call", "narrate")


def test_retry_and_fallback_callbacks_are_traced():
    tracer = Tracer()
    tracer.on_retry(RetryNotice(2, 1.5, RuntimeError("busy")))
    tracer.on_fallback(FallbackNotice("narrate", "a:m1", "b:m2", RuntimeError("down"), cooled=True))
    retry, fallback = tracer.records()
    assert retry.payload == {"attempt": 2, "delay": 1.5, "error": "busy"}
    assert fallback.payload["failed"] == "a:m1" and fallback.payload["next"] == "b:m2" and fallback.payload["cooling_down"]


def test_a_check_turn_with_a_repair_is_traced_end_to_end():
    game = traced_game([reply(["You creep."], check=stealth_check()), reply(["Done."], BAD), FIX])
    run(turn(game, "I sneak."))
    records = game.tracer.records()
    assert [r.kind for r in records] == [
        "llm.call", "check.workings", "llm.call", "changes.proposed", "changes.rejected", "llm.call",
        "changes.accepted", "state.diff"]
    assert {r.turn_id for r in records} == {1}
    call = records[0].payload
    assert call["task"] == "narrate" and call["system"] and call["messages"][-1]["content"].endswith("I sneak.")
    assert "You creep." in call["reply"] and call["usage"]["latency"] >= 0
    workings = records[1].payload
    assert (workings["tier"], workings["difficulty"], workings["die"], workings["total"]) == ("easy", 12, 14, 15)
    assert records[2].payload["task"] == "check_outcome" and records[5].payload["task"] == "repair"
    assert records[6].payload["repaired"] is True and records[7].payload["events"][0]["kind"] == "entity.updated"


def test_an_unreadable_reply_is_traced_with_its_raw_text():
    game = traced_game(["not json at all"])
    run(turn(game, "I wave."))
    assert [r.kind for r in game.tracer.records()] == ["llm.call", "reply.invalid"]
    assert game.tracer.records()[0].payload["reply"] == "not json at all"


def test_dev_role_reads_and_follows_the_trace_but_players_cannot():
    server = LocalServer(traced_game([reply(["One."]), reply(["Two."])]), dev_enabled=True)
    dev, player = server.connect(Role.DEV), server.connect(Role.PLAYER)
    with pytest.raises(RoleError):
        player.send(GetTrace())

    async def scenario():
        async for _ in player.send(SubmitAction("first")):
            pass
        past = [e.event async for e in dev.send(GetTrace())]
        live, seen_by_player = [], []

        async def follow(session, into):
            async for envelope in session.subscribe(since=len(server._log)):
                into.append(envelope)

        tasks = [asyncio.create_task(follow(dev, live)), asyncio.create_task(follow(player, seen_by_player))]
        await asyncio.sleep(0)
        async for _ in player.send(SubmitAction("second")):
            pass
        await asyncio.sleep(0)
        await dev.close()
        await player.close()
        await asyncio.wait_for(asyncio.gather(*tasks), 1)
        return past, live, seen_by_player

    past, live, seen_by_player = run(scenario())
    traced = [e for e in past if isinstance(e, TraceEvent)]
    assert [e.kind for e in traced] == ["llm.call"] and traced[0].turn_id == 1 and traced[0].trace_seq == 1
    assert [e.event.kind for e in live if isinstance(e.event, TraceEvent)] == ["llm.call"]
    assert not any(isinstance(e.event, TraceEvent) for e in seen_by_player)


def test_get_trace_filters_by_turn_and_since():
    server = LocalServer(traced_game([reply(["One."]), reply(["Two."])]), dev_enabled=True)
    dev = server.connect(Role.DEV)

    async def scenario():
        for text in ("first", "second"):
            async for _ in dev.send(SubmitAction(text)):
                pass
        return ([e.event async for e in dev.send(GetTrace(turn=2))], [e.event async for e in dev.send(GetTrace(since=1))])

    second, after_first = run(scenario())
    assert [e.turn_id for e in second if isinstance(e, TraceEvent)] == [2]
    assert [e.trace_seq for e in after_first if isinstance(e, TraceEvent)] == [2]


def test_trace_stays_out_of_the_log_when_dev_is_disabled():
    server = LocalServer(traced_game([reply(["One."])]), dev_enabled=False)
    run(turn(server.game, "first"))
    assert server._log == [] and len(server.game.tracer.records()) == 1


def test_timeline_shows_offsets_summaries_and_optionally_payloads():
    tracer = Tracer()
    tracer.emit("llm.call", {"task": "narrate", "variant": "base", "model": "m", "usage": {
        "latency": 1.2, "time_to_first_token": 0.4, "prompt_tokens": 800, "output_tokens": 90, "cached_tokens": 600}}, turn=1)
    tracer.emit("check.workings", {"skill": "stealth", "tier": "easy", "base": 10, "adjustments": [
        {"what": "dim light", "delta": 1}], "difficulty": 11, "die": 14, "modifier": 1, "total": 15,
        "classification": "success"}, turn=1)
    text = format_timeline(tracer.records())
    assert "narrate, base, m, 1.20s, first token 0.40s, 800 in / 90 out, 600 cached" in text
    assert "stealth easy (base 10, dim light +1) = difficulty 11; rolled 14 +1 = 15 (success)" in text
    assert text.splitlines()[0].startswith("+  0.000s") and '"task": "narrate"' not in text
    assert '"task": "narrate"' in format_timeline(tracer.records(), full=True)
    assert format_timeline([]) == "(nothing traced)"


def inspect_session(inputs, role):
    out, lines = [], iter(inputs)

    async def ask(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    game = traced_game([reply(["One."]), reply(["Two."])])
    session = LocalServer(game, dev_enabled=True).connect(role)
    run(play(session, ask, lambda text="", end="\n": out.append(text + end), opening=False))
    return "".join(out)


def test_inspect_prints_the_last_turn_for_the_dev_role_only():
    text = inspect_session(["first", "second", "/inspect", "/inspect 1 full", "/quit"], Role.DEV)
    assert text.count("Turn 2") == 1 and "Turn 1" in text and '"system"' in text and "llm.call" in text
    assert "Unknown command /inspect" in inspect_session(["/inspect", "/quit"], Role.PLAYER)
