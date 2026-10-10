"""Tests for the world id and the dev store: dev notes and the persisted trace."""

import pytest

from aimaginarium.devstore import BLOB_MIN, DevStore
from aimaginarium.trace import TraceRecord, Tracer
from aimaginarium.world import WorldStore

LONG = "The system prompt, repeated every turn. " * 40


def record(seq, turn, kind="llm.call", **payload):
    return TraceRecord(seq, f"2026-10-10T10:00:{seq:02d}+00:00", turn, kind, payload)


# -- the world id ---------------------------------------------------------

def test_a_world_has_a_stable_id_that_survives_reopening_the_file(tmp_path):
    path = tmp_path / "w.sqlite"
    with WorldStore.open(path) as store:
        world_id = store.world_id
        assert world_id == store.world_id and len(world_id) == 32
    with WorldStore.open(path) as store:
        assert store.world_id == world_id


def test_two_worlds_have_different_ids_and_a_copy_can_be_given_a_new_one(tmp_path):
    with WorldStore.open() as a, WorldStore.open() as b:
        assert a.world_id != b.world_id
        before = a.world_id
        assert a.new_world_id() != before and a.world_id != before


def test_the_id_is_made_on_demand_without_touching_the_schema_version(tmp_path):
    path = tmp_path / "old.sqlite"
    with WorldStore.open(path) as store:                       # a world made before ids existed has no meta table
        assert not store.connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone()
        version = store.connection.execute("PRAGMA user_version").fetchone()[0]
        store.world_id
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == version


# -- the trace --------------------------------------------------------------

def test_the_trace_is_kept_across_runs_and_read_by_turn_with_its_neighbours(tmp_path):
    path = tmp_path / "dev.sqlite"
    with DevStore.open(path) as dev:
        tracer = Tracer()
        tracer.add_sink(dev.trace_sink("w1"))
        for turn in (1, 2, 3, 4):
            tracer.emit("llm.call", {"turn": turn}, turn=turn)
        tracer.emit("note", {"no": "turn"})
    with DevStore.open(path) as dev:                           # a new run: the in-memory buffer is gone, this is not
        assert [r.turn_id for r in dev.trace("w1", 3)] == [3]
        assert [r.turn_id for r in dev.trace("w1", 3, around=1)] == [2, 3, 4]
        assert [r.payload["turn"] for r in dev.trace("w1", 1, around=5) if r.turn_id] == [1, 2, 3, 4]
        assert len(dev.trace("w1")) == 5 and dev.trace("w1", 99) == []


def test_each_world_and_each_run_keeps_its_own_records():
    with DevStore.open() as dev:
        one, two = dev.trace_sink("w1"), dev.trace_sink("w2")
        again = dev.trace_sink("w1")                           # a second run of the program: sequence numbers restart
        one(record(1, 1, run="a"))
        two(record(1, 1, run="b"))
        again(record(1, 2, run="c"))
        assert [r.payload["run"] for r in dev.trace("w1")] == ["a", "c"]
        assert [r.payload["run"] for r in dev.trace("w2")] == ["b"]


def test_long_text_is_stored_once_and_comes_back_exactly():
    with DevStore.open() as dev:
        sink = dev.trace_sink("w")
        for turn in range(1, 21):
            sink(record(turn, turn, system=LONG, messages=[{"role": "user", "content": LONG + str(turn)}], short="hi"))
        stored = dev._conn.execute("SELECT SUM(LENGTH(payload)) FROM trace").fetchone()[0]
        assert stored < 20 * 300                               # 20 records of ~3.2 KB each (64 KB), kept as references
        assert dev._conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 21   # the system prompt once, 20 messages
        back = dev.trace("w", 7)[0].payload
        assert back == {"system": LONG, "messages": [{"role": "user", "content": LONG + "7"}], "short": "hi"}
    assert len(LONG) > BLOB_MIN


def test_a_payload_that_looks_like_a_reference_is_not_confused_with_one():
    with DevStore.open() as dev:
        dev.trace_sink("w")(record(1, 1, odd={"$blob": "not-a-hash"}))
        assert dev.trace("w", 1)[0].payload == {"odd": ""}     # unknown hashes read back empty rather than failing


# -- dev notes ---------------------------------------------------------------

def test_a_note_is_attached_to_a_turn_with_tags_an_anchor_and_an_excerpt():
    with DevStore.open() as dev:
        note = dev.add_note("w", 12, "  The cellar moved.  ", tags=("continuity", "world"),
                            anchor={"trace_seq": 7}, excerpt="> I leave")
        assert (note.turn_id, note.text, note.tags, note.anchor, note.excerpt) == \
            (12, "The cellar moved.", ("continuity", "world"), {"trace_seq": 7}, "> I leave")
        assert note.status == "open" and note.author == "developer" and note.world_id == "w"
        assert dev.note(note.id) == note and note.to_dict()["tags"] == ["continuity", "world"]


def test_a_note_needs_text_and_an_unknown_note_is_an_error():
    with DevStore.open() as dev:
        with pytest.raises(ValueError):
            dev.add_note("w", 1, "   ")
        for call in (lambda: dev.note(5), lambda: dev.update_note(5, text="x"), lambda: dev.delete_note(5)):
            with pytest.raises(KeyError):
                call()


def test_notes_are_listed_per_world_and_filtered_by_turn_tag_and_status():
    with DevStore.open() as dev:
        a = dev.add_note("w", 1, "a", tags=("tone",))
        b = dev.add_note("w", 2, "b", tags=("continuity", "tone"))
        c = dev.add_note("w", 2, "c")
        dev.add_note("other", 2, "elsewhere")
        dev.update_note(c.id, status="resolved", resolution="fixed in #200")
        assert [n.id for n in dev.notes("w")] == [a.id, b.id, c.id]
        assert [n.id for n in dev.notes("w", turn=2)] == [b.id, c.id]
        assert [n.id for n in dev.notes("w", tag="tone")] == [a.id, b.id]
        assert [n.id for n in dev.notes("w", status="resolved")] == [c.id]
        assert dev.note(c.id).resolution == "fixed in #200" and len(dev.notes("w", limit=1)) == 1


def test_a_note_can_be_edited_and_deleted_and_only_what_is_given_changes():
    with DevStore.open() as dev:
        note = dev.add_note("w", 1, "old", tags=("x",))
        edited = dev.update_note(note.id, text="new")
        assert (edited.text, edited.tags, edited.status) == ("new", ("x",), "open")
        assert dev.update_note(note.id, tags=("y", "z")).tags == ("y", "z")
        for bad in (dict(text=" "), dict(status="done")):
            with pytest.raises(ValueError):
                dev.update_note(note.id, **bad)
        dev.delete_note(note.id)
        assert dev.notes("w") == []


def test_notes_are_kept_when_the_file_is_reopened(tmp_path):
    path = tmp_path / "dev.sqlite"
    with DevStore.open(path) as dev:
        dev.add_note("w", 3, "keep me")
    with DevStore.open(path) as dev:
        assert [n.text for n in dev.notes("w")] == ["keep me"]
