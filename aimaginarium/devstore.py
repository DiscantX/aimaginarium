"""The dev store: what the developer keeps about the game, outside the game.

Dev notes and the full trace live here, in a file of their own and never in a world's database, so nothing in
it can reach an LLM prompt or the authoritative world state. One store serves every world a developer plays:
rows are keyed by the world's id (:attr:`~aimaginarium.world.WorldStore.world_id`) and turn id, because turn
ids are only unique within a world.

The trace is kept in full (prompts and replies included). Long strings, which repeat from turn to turn (the
system prompt, the history), are stored once and referred to by hash.
"""

from __future__ import annotations

import hashlib
import os
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from .trace import TraceRecord, turn_in_range

SCHEMA_VERSION = 1
BLOB_MIN = 400
"""Strings at least this long are stored once, by hash, and referred to from each record that has them."""

_SCHEMA = """
CREATE TABLE trace (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id TEXT NOT NULL,
    session  TEXT NOT NULL,
    seq      INTEGER NOT NULL,
    at       TEXT NOT NULL,
    turn_id  INTEGER,
    kind     TEXT NOT NULL,
    payload  TEXT NOT NULL
);
CREATE INDEX trace_turn ON trace (world_id, turn_id);
CREATE TABLE blobs (hash TEXT PRIMARY KEY, text TEXT NOT NULL);
CREATE TABLE dev_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   TEXT NOT NULL,
    turn_id    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    tags       TEXT NOT NULL,
    anchor     TEXT,
    excerpt    TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'open',
    resolution TEXT NOT NULL DEFAULT '',
    author     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX dev_notes_turn ON dev_notes (world_id, turn_id);
"""

STATUSES = ("open", "resolved")


@dataclass(frozen=True)
class DevNote:
    """A thing the developer noticed about a turn.

    Not a player note: those are the player's own notes on the story and belong to the game.

    Attributes:
        id: The note's id.
        world_id: The world it is about.
        turn_id: The turn it is attached to.
        text: What was noticed.
        tags: Free labels such as ``continuity`` or ``tone``.
        anchor: Where in the turn it points, such as ``{"trace_seq": 7}``; None for the turn as a whole.
        excerpt: A short piece of the turn (or the selected text) that keeps the note readable on its own.
        status: ``open`` or ``resolved``.
        resolution: How it was resolved, such as ``fixed in #123``.
        author: ``developer`` or ``claude``.
        created_at: UTC, ISO 8601.
        updated_at: UTC, ISO 8601.
    """

    id: int
    world_id: str
    turn_id: int
    text: str
    tags: tuple[str, ...]
    anchor: Optional[dict[str, Any]]
    excerpt: str
    status: str
    resolution: str
    author: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Returns the note as a plain dict (the wire form)."""
        return {**asdict(self), "tags": list(self.tags)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _pack(value: Any, conn: sqlite3.Connection) -> Any:
    """Replaces long strings with ``{"$blob": hash}``, storing each text once."""
    if isinstance(value, str):
        if len(value) < BLOB_MIN:
            return value
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        conn.execute("INSERT OR IGNORE INTO blobs (hash, text) VALUES (?, ?)", (digest, value))
        return {"$blob": digest}
    if isinstance(value, dict):
        return {k: _pack(v, conn) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_pack(v, conn) for v in value]
    return value


def _unpack(value: Any, conn: sqlite3.Connection) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$blob"}:
            row = conn.execute("SELECT text FROM blobs WHERE hash = ?", (value["$blob"],)).fetchone()
            return row[0] if row else ""
        return {k: _unpack(v, conn) for k, v in value.items()}
    if isinstance(value, list):
        return [_unpack(v, conn) for v in value]
    return value


class TraceSink:
    """A tracer sink that keeps every record in the dev store, for one world and one run of the program."""

    def __init__(self, store: "DevStore", world_id: str):
        self._store, self._world_id, self._session = store, world_id, uuid.uuid4().hex[:8]

    def __call__(self, record: TraceRecord) -> None:
        self._store.add_trace(self._world_id, self._session, record)


class DevStore:
    """The developer's notes and the persisted trace, in one SQLite file (or in memory)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @classmethod
    def open(cls, path: Union[str, "os.PathLike[str]"] = ":memory:") -> "DevStore":
        """Opens the store, creating the file (and its folder) if it is new."""
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            conn.executescript("BEGIN;" + _SCHEMA + f"PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
        elif version != SCHEMA_VERSION:
            conn.close()
            raise RuntimeError(f"unsupported dev store version {version}")
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DevStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- the trace -------------------------------------------------------

    def trace_sink(self, world_id: str) -> TraceSink:
        """A sink to add to a :class:`~aimaginarium.trace.Tracer`, so everything it traces is kept."""
        return TraceSink(self, world_id)

    def add_trace(self, world_id: str, session: str, record: TraceRecord) -> None:
        """Keeps one trace record."""
        payload = json.dumps(_pack(record.payload, self._conn), default=str, ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO trace (world_id, session, seq, at, turn_id, kind, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (world_id, session, record.seq, record.at, record.turn_id, record.kind, payload))

    def trace(self, world_id: str, turn: Optional[int] = None, around: int = 0, limit: int = 1000) -> list[TraceRecord]:
        """The kept trace of a world, oldest first: all of it, or one turn (plus ``around`` turns each side)."""
        rows = self._conn.execute("SELECT * FROM trace WHERE world_id = ? ORDER BY id LIMIT ?", (world_id, limit)).fetchall() \
            if turn is None else self._conn.execute(
            "SELECT * FROM trace WHERE world_id = ? AND turn_id BETWEEN ? AND ? ORDER BY id",
            (world_id, turn - around, turn + around)).fetchall()
        rows = [r for r in rows if turn_in_range(r["turn_id"], turn, around)]
        return [TraceRecord(r["seq"], r["at"], r["turn_id"], r["kind"], _unpack(json.loads(r["payload"]), self._conn))
                for r in rows[:limit]]

    # -- dev notes -------------------------------------------------------

    def add_note(self, world_id: str, turn_id: int, text: str, *, tags: tuple[str, ...] = (),
                 anchor: Optional[dict[str, Any]] = None, excerpt: str = "", author: str = "developer") -> DevNote:
        """Adds a note to a turn.

        Raises:
            ValueError: If the text is empty.
        """
        if not text.strip():
            raise ValueError("a dev note needs some text")
        now = _now()
        cursor = self._conn.execute(
            "INSERT INTO dev_notes (world_id, turn_id, text, tags, anchor, excerpt, author, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (world_id, turn_id, text.strip(), json.dumps(list(tags)), json.dumps(anchor) if anchor else None,
             excerpt, author, now, now))
        return self.note(cursor.lastrowid)

    def note(self, note_id: int) -> DevNote:
        """One note by id.

        Raises:
            KeyError: If there is none.
        """
        row = self._conn.execute("SELECT * FROM dev_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise KeyError(f"no dev note {note_id}")
        return self._note(row)

    def notes(self, world_id: str, turn: Optional[int] = None, tag: Optional[str] = None,
              status: Optional[str] = None, limit: int = 200) -> list[DevNote]:
        """A world's notes, oldest first, optionally of one turn, tag or status."""
        sql, args = "SELECT * FROM dev_notes WHERE world_id = ?", [world_id]
        if turn is not None:
            sql += " AND turn_id = ?"
            args.append(turn)
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY id"
        notes = [self._note(r) for r in self._conn.execute(sql, args)]
        return [n for n in notes if tag is None or tag in n.tags][:limit]

    def update_note(self, note_id: int, *, text: Optional[str] = None, tags: Optional[tuple[str, ...]] = None,
                    status: Optional[str] = None, resolution: Optional[str] = None) -> DevNote:
        """Edits a note; only what is given changes.

        Raises:
            KeyError: If there is no such note.
            ValueError: If the text is empty or the status unknown.
        """
        current = self.note(note_id)
        if text is not None and not text.strip():
            raise ValueError("a dev note needs some text")
        if status is not None and status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        self._conn.execute(
            "UPDATE dev_notes SET text = ?, tags = ?, status = ?, resolution = ?, updated_at = ? WHERE id = ?",
            (current.text if text is None else text.strip(), json.dumps(list(current.tags if tags is None else tags)),
             current.status if status is None else status,
             current.resolution if resolution is None else resolution, _now(), note_id))
        return self.note(note_id)

    def delete_note(self, note_id: int) -> None:
        """Deletes a note.

        Raises:
            KeyError: If there is no such note.
        """
        self.note(note_id)
        self._conn.execute("DELETE FROM dev_notes WHERE id = ?", (note_id,))

    @staticmethod
    def _note(row: sqlite3.Row) -> DevNote:
        return DevNote(row["id"], row["world_id"], row["turn_id"], row["text"], tuple(json.loads(row["tags"])),
                       json.loads(row["anchor"]) if row["anchor"] else None, row["excerpt"], row["status"],
                       row["resolution"], row["author"], row["created_at"], row["updated_at"])
