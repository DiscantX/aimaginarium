"""The world store: current state plus an append-only event log.

All writes go through :meth:`WorldStore.commit`. A commit validates each change,
appends one event per change, and updates the state tables in a single
transaction, so the log and the state cannot disagree and a rejected commit
leaves nothing behind. The store holds ground truth; it does not filter by what
any player knows (that is the projection layer's job).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence, Union

from pydantic import ValidationError

from .apply import apply_event, dumps
from .changes import Change, parse_changes
from .models import ChangeError, CommitError, CommitResult, Entity, Event, Fact, Rejected
from .plan import Planner
from .schema import LOG_SCHEMA, SCHEMA_VERSION, STATE_SCHEMA


class WorldStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # -- lifecycle -------------------------------------------------------

    @classmethod
    def open(cls, path: Union[str, os.PathLike] = ":memory:") -> "WorldStore":
        """Open a world database, creating it if it is new."""
        conn = sqlite3.connect(str(path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            conn.executescript("BEGIN;" + STATE_SCHEMA + LOG_SCHEMA + f"PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
        elif version != SCHEMA_VERSION:
            conn.close()
            raise RuntimeError(f"unsupported world database version {version}")
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "WorldStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # -- writing ---------------------------------------------------------

    def new_turn(self) -> int:
        """Allocate the next turn id, used to group the events of one player turn."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO counters (name, value) VALUES ('turn', 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1"
            )
            value = self._conn.execute("SELECT value FROM counters WHERE name = 'turn'").fetchone()[0]
            self._conn.execute("COMMIT")
            return value
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def commit(
        self,
        changes: Sequence[Union[Change, dict[str, Any]]],
        *,
        actor: str,
        turn: Optional[int] = None,
        causes: Iterable[int] = (),
        world_time: Optional[int] = None,
    ) -> CommitResult:
        """Validate and commit changes atomically.

        Every change becomes one event sharing the actor, turn, world time and
        causes. Raises :class:`CommitError` (with the first failing change) and
        writes nothing if any change is rejected.
        """
        if not actor or not actor.strip():
            raise CommitError([ChangeError(-1, "invalid_actor", "actor must not be empty")])
        if not changes:
            raise CommitError([ChangeError(-1, "empty_commit", "a commit needs at least one change")])
        try:
            parsed = parse_changes([c.model_dump() if hasattr(c, "model_dump") else c for c in changes])
        except ValidationError as exc:
            raise CommitError([ChangeError(-1, "invalid_change", str(exc))]) from exc
        cause_list = list(dict.fromkeys(causes))

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for seq in cause_list:
                if conn.execute("SELECT 1 FROM events WHERE seq = ?", (seq,)).fetchone() is None:
                    raise CommitError([ChangeError(-1, "unknown_cause", f"cause event {seq} does not exist")])
            planner = Planner(conn)
            events: list[Event] = []
            for index, change in enumerate(parsed):
                try:
                    draft = planner.plan(change)
                except Rejected as exc:
                    raise CommitError([ChangeError(index, exc.code, exc.message)]) from exc
                created_at = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute(
                    "INSERT INTO events (turn_id, actor_id, kind, world_time, payload, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (turn, actor, draft.kind, world_time, dumps(draft.payload), created_at),
                )
                seq = cursor.lastrowid
                for cause in cause_list:
                    conn.execute("INSERT INTO event_causes (event_seq, cause_seq) VALUES (?, ?)", (seq, cause))
                for entity_id in dict.fromkeys(draft.entities):
                    conn.execute("INSERT INTO event_entities (event_seq, entity_id) VALUES (?, ?)", (seq, entity_id))
                apply_event(conn, seq, draft.kind, draft.payload)
                events.append(
                    Event(seq, turn, actor, draft.kind, world_time, json.loads(dumps(draft.payload)),
                          tuple(cause_list), created_at)
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return CommitResult(tuple(events), dict(planner.refs))

    # -- reading entities ------------------------------------------------

    def _entity_from_row(self, row: sqlite3.Row, with_facts: bool = True) -> Entity:
        return Entity(
            id=row["id"], kind=row["kind"], name=row["name"], parent_id=row["parent_id"],
            data=json.loads(row["data"]), created_seq=row["created_seq"], updated_seq=row["updated_seq"],
            removed_seq=row["removed_seq"],
            established=tuple(self.facts(row["id"])) if with_facts else (),
        )

    def get_entity(self, entity_id: str, *, include_removed: bool = False) -> Optional[Entity]:
        row = self._conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None or (row["removed_seq"] is not None and not include_removed):
            return None
        return self._entity_from_row(row)

    def children(self, parent_id: Optional[str], *, kind: Optional[str] = None) -> list[Entity]:
        """What is directly inside an entity (pass ``None`` for top-level entities)."""
        sql = "SELECT * FROM entities WHERE removed_seq IS NULL AND "
        args: list[Any] = []
        if parent_id is None:
            sql += "parent_id IS NULL"
        else:
            sql += "parent_id = ?"
            args.append(parent_id)
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY created_seq, id"
        return [self._entity_from_row(r) for r in self._conn.execute(sql, args)]

    def find(self, *, kind: Optional[str] = None, name: Optional[str] = None) -> list[Entity]:
        """Entities by kind and/or exact name (case-insensitive)."""
        sql, args = "SELECT * FROM entities WHERE removed_seq IS NULL", []
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        if name is not None:
            sql += " AND name = ? COLLATE NOCASE"
            args.append(name)
        sql += " ORDER BY created_seq, id"
        return [self._entity_from_row(r) for r in self._conn.execute(sql, args)]

    def ancestors(self, entity_id: str) -> list[str]:
        """Ids from the entity's parent up to the root."""
        chain: list[str] = []
        cursor = self._conn.execute("SELECT parent_id FROM entities WHERE id = ?", (entity_id,)).fetchone()
        parent = cursor[0] if cursor else None
        while parent is not None:
            chain.append(parent)
            parent = self._conn.execute("SELECT parent_id FROM entities WHERE id = ?", (parent,)).fetchone()[0]
        return chain

    def location_of(self, entity_id: str) -> Optional[str]:
        """The nearest enclosing location of an entity, if any."""
        for ancestor in self.ancestors(entity_id):
            if self._conn.execute("SELECT kind FROM entities WHERE id = ?", (ancestor,)).fetchone()[0] == "location":
                return ancestor
        return None

    def connections(self, from_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT c.* FROM connections c JOIN entities e ON e.id = c.to_id "
            "WHERE c.from_id = ? AND e.removed_seq IS NULL ORDER BY c.to_id, c.label",
            (from_id,),
        )
        return [
            {"from_id": r["from_id"], "to_id": r["to_id"], "label": r["label"], "data": json.loads(r["data"])}
            for r in rows
        ]

    # -- reading facts ---------------------------------------------------

    def _fact_from_row(self, row: sqlite3.Row) -> Fact:
        known = None
        if row["visibility"] == "restricted":
            known = tuple(self.knowers(row["id"]))
        return Fact(
            id=row["id"], entity_id=row["entity_id"], text=row["text"], visibility=row["visibility"],
            created_seq=row["created_seq"], superseded_seq=row["superseded_seq"], known_by=known,
        )

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        row = self._conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return self._fact_from_row(row) if row else None

    def facts(self, entity_id: str, *, include_superseded: bool = False) -> list[Fact]:
        sql = "SELECT * FROM facts WHERE entity_id = ?"
        if not include_superseded:
            sql += " AND superseded_seq IS NULL"
        return [self._fact_from_row(r) for r in self._conn.execute(sql + " ORDER BY created_seq, id", (entity_id,))]

    def knowers(self, fact_id: str) -> list[str]:
        """Direct knowers of a restricted fact, in the order they learned it."""
        rows = self._conn.execute(
            "SELECT knower_id FROM fact_knowers WHERE fact_id = ? ORDER BY event_seq, knower_id", (fact_id,)
        )
        return [r[0] for r in rows]

    def known_facts(self, knower_id: str, *, include_superseded: bool = False) -> list[Fact]:
        """Restricted facts this character (or group) knows directly. Group membership is resolved elsewhere."""
        sql = "SELECT f.* FROM facts f JOIN fact_knowers k ON k.fact_id = f.id WHERE k.knower_id = ?"
        if not include_superseded:
            sql += " AND f.superseded_seq IS NULL"
        return [self._fact_from_row(r) for r in self._conn.execute(sql + " ORDER BY f.created_seq, f.id", (knower_id,))]

    # -- reading the log -------------------------------------------------

    def _event_from_row(self, row: sqlite3.Row) -> Event:
        causes = tuple(
            r[0] for r in self._conn.execute(
                "SELECT cause_seq FROM event_causes WHERE event_seq = ? ORDER BY cause_seq", (row["seq"],)
            )
        )
        return Event(
            seq=row["seq"], turn_id=row["turn_id"], actor_id=row["actor_id"], kind=row["kind"],
            world_time=row["world_time"], payload=json.loads(row["payload"]), causes=causes,
            created_at=row["created_at"],
        )

    def get_event(self, seq: int) -> Optional[Event]:
        row = self._conn.execute("SELECT * FROM events WHERE seq = ?", (seq,)).fetchone()
        return self._event_from_row(row) if row else None

    def events(
        self,
        *,
        after: int = 0,
        kind: Optional[str] = None,
        actor: Optional[str] = None,
        entity: Optional[str] = None,
        turn: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[Event]:
        """Events in commit order. ``entity`` selects every event that touched that entity."""
        sql, args = "SELECT e.* FROM events e WHERE e.seq > ?", [after]
        if kind is not None:
            sql += " AND e.kind = ?"
            args.append(kind)
        if actor is not None:
            sql += " AND e.actor_id = ?"
            args.append(actor)
        if turn is not None:
            sql += " AND e.turn_id = ?"
            args.append(turn)
        if entity is not None:
            sql += " AND e.seq IN (SELECT event_seq FROM event_entities WHERE entity_id = ?)"
            args.append(entity)
        sql += " ORDER BY e.seq"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return [self._event_from_row(r) for r in self._conn.execute(sql, args)]

    def causal_chain(self, seq: int) -> list[Event]:
        """Everything that led to an event (its causes, their causes, and so on), oldest first."""
        seen: set[int] = set()
        frontier = [seq]
        while frontier:
            rows = self._conn.execute(
                f"SELECT cause_seq FROM event_causes WHERE event_seq IN ({','.join('?' * len(frontier))})", frontier
            )
            frontier = [r[0] for r in rows if r[0] not in seen]
            seen.update(frontier)
        return [e for e in (self.get_event(s) for s in sorted(seen)) if e is not None]
