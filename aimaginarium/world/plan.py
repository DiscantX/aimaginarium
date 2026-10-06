"""Validate one change against the current state and turn it into an event draft.

Checks here are structural and state-consistency checks (do the referenced ids
exist, would containment form a cycle). Rules legality belongs to the ruleset
and fictional feasibility to the LLM; neither is the store's business.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import paths
from .apply import dumps
from .changes import (
    Change, Connect, Create, Disconnect, Establish, Move, Record, Remove, Reveal, Supersede, Update,
)
from .models import Rejected

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_PREFIXES = {"character": "char", "item": "item", "location": "loc"}
RESERVED_KIND_PREFIXES = ("entity.", "fact.", "connection.")


@dataclass
class Draft:
    kind: str
    payload: dict[str, Any]
    entities: list[str] = field(default_factory=list)


class Planner:
    """Plans the changes of one commit in order; later changes see earlier ones."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.refs: dict[str, str] = {}

    # -- helpers ---------------------------------------------------------

    def _resolve(self, value: str) -> str:
        if value.startswith("@"):
            if value not in self.refs:
                raise Rejected("unknown_ref", f"{value} was not created earlier in this commit")
            return self.refs[value]
        return value

    def _bind(self, ref: str | None, real_id: str) -> None:
        if ref is None:
            return
        if not ref.startswith("@") or len(ref) < 2:
            raise Rejected("invalid_ref", f"ref must look like '@name', got {ref!r}")
        if ref in self.refs:
            raise Rejected("duplicate_ref", f"{ref} is already used in this commit")
        self.refs[ref] = real_id

    def _next(self, name: str) -> int:
        self.conn.execute(
            "INSERT INTO counters (name, value) VALUES (?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1",
            (name,),
        )
        return self.conn.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()[0]

    def _exists(self, entity_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone() is not None

    def _entity(self, entity_id: str, what: str = "entity") -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise Rejected("unknown_entity", f"{what} {entity_id!r} does not exist")
        if row["removed_seq"] is not None:
            raise Rejected("removed_entity", f"{what} {entity_id!r} has been removed")
        return row

    def _fact(self, fact_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        if row is None:
            raise Rejected("unknown_fact", f"fact {fact_id!r} does not exist")
        return row

    @staticmethod
    def _json(value: Any, what: str) -> None:
        try:
            dumps(value)
        except (TypeError, ValueError) as exc:
            raise Rejected("invalid_json", f"{what} is not valid JSON data: {exc}")

    # -- dispatch --------------------------------------------------------

    def plan(self, change: Change) -> Draft:
        handler = getattr(self, "_plan_" + change.op)
        return handler(change)

    # -- entities --------------------------------------------------------

    def _plan_create(self, c: Create) -> Draft:
        if not c.kind.strip() or not c.name.strip():
            raise Rejected("invalid_entity", "kind and name must not be empty")
        if paths.RESERVED_ROOT in c.data:
            raise Rejected("reserved_path", "facts are not stored in data; use an establish change")
        self._json(c.data, "data")
        parent = self._resolve(c.parent_id) if c.parent_id is not None else None
        if parent is not None:
            self._entity(parent, "parent")
        if c.id is not None:
            entity_id = c.id
            if not _ID_PATTERN.match(entity_id):
                raise Rejected("invalid_id", f"id {entity_id!r} must match {_ID_PATTERN.pattern}")
            if self._exists(entity_id):
                raise Rejected("duplicate_id", f"id {entity_id!r} already exists")
        else:
            prefix = _PREFIXES.get(c.kind, re.sub(r"[^a-z0-9]+", "-", c.kind.lower()).strip("-") or "entity")
            while True:
                entity_id = f"{prefix}-{self._next('id:' + prefix)}"
                if not self._exists(entity_id):
                    break
        self._bind(c.ref, entity_id)
        payload = {"id": entity_id, "kind": c.kind, "name": c.name, "parent_id": parent, "data": c.data}
        return Draft("entity.created", payload, [entity_id] + ([parent] if parent else []))

    def _plan_update(self, c: Update) -> Draft:
        entity_id = self._resolve(c.entity)
        row = self._entity(entity_id)
        if c.name is None and not c.set and not c.unset:
            raise Rejected("empty_update", "an update must rename, set or unset something")
        if c.name is not None and not c.name.strip():
            raise Rejected("invalid_entity", "name must not be empty")
        self._json(c.set, "set")
        data = json.loads(row["data"])
        changes: list[dict[str, Any]] = []
        for path, value in c.set.items():
            segments = paths.split(path)
            found, old = paths.get(data, segments)
            try:
                paths.set_value(data, segments, value)
            except paths.PathBlocked as exc:
                raise Rejected("path_blocked", f"{path!r} runs through {exc} which is not an object")
            record: dict[str, Any] = {"path": path, "op": "set", "new": value}
            if found:
                record["old"] = copy.deepcopy(old)
            changes.append(record)
        for path in c.unset:
            segments = paths.split(path)
            found, old = paths.get(data, segments)
            if not found:
                raise Rejected("path_missing", f"{path!r} is not set on {entity_id}")
            paths.unset_value(data, segments)
            changes.append({"path": path, "op": "unset", "old": copy.deepcopy(old)})
        payload: dict[str, Any] = {"id": entity_id, "changes": changes}
        if c.name is not None:
            payload["name"] = {"old": row["name"], "new": c.name}
        return Draft("entity.updated", payload, [entity_id])

    def _plan_move(self, c: Move) -> Draft:
        entity_id = self._resolve(c.entity)
        row = self._entity(entity_id)
        target = self._resolve(c.to) if c.to is not None else None
        if target == row["parent_id"]:
            raise Rejected("no_change", f"{entity_id} is already there")
        if target is not None:
            self._entity(target, "destination")
            cursor: str | None = target
            while cursor is not None:
                if cursor == entity_id:
                    raise Rejected("containment_cycle", f"{entity_id} cannot be placed inside itself")
                cursor = self.conn.execute("SELECT parent_id FROM entities WHERE id = ?", (cursor,)).fetchone()[0]
        payload = {"id": entity_id, "from": row["parent_id"], "to": target}
        return Draft("entity.moved", payload, [x for x in (entity_id, row["parent_id"], target) if x])

    def _plan_remove(self, c: Remove) -> Draft:
        entity_id = self._resolve(c.entity)
        row = self._entity(entity_id)
        n = self.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE parent_id = ? AND removed_seq IS NULL", (entity_id,)
        ).fetchone()[0]
        if n:
            raise Rejected("has_children", f"{entity_id} still contains {n} entities; move or remove them first")
        links = [
            {"from_id": r["from_id"], "to_id": r["to_id"], "label": r["label"], "data": json.loads(r["data"])}
            for r in self.conn.execute(
                "SELECT * FROM connections WHERE from_id = ? OR to_id = ? ORDER BY from_id, to_id, label",
                (entity_id, entity_id),
            )
        ]
        payload = {"id": entity_id, "parent_id": row["parent_id"], "connections_removed": links}
        touched = [entity_id] + ([row["parent_id"]] if row["parent_id"] else [])
        return Draft("entity.removed", payload, touched)

    # -- facts -----------------------------------------------------------

    def _plan_establish(self, c: Establish) -> Draft:
        entity_id = self._resolve(c.entity)
        self._entity(entity_id)
        if not c.text.strip():
            raise Rejected("invalid_fact", "fact text must not be empty")
        knowers: list[str] | None = None
        if c.known_by is not None:
            knowers = []
            for k in c.known_by:
                k = self._resolve(k)
                self._entity(k, "knower")
                if k not in knowers:
                    knowers.append(k)
        fact_id = f"f-{self._next('fact')}"
        self._bind(c.ref, fact_id)
        payload = {
            "fact_id": fact_id,
            "entity_id": entity_id,
            "text": c.text,
            "visibility": "public" if knowers is None else "restricted",
            "known_by": knowers,
        }
        return Draft("fact.established", payload, [entity_id] + (knowers or []))

    def _plan_supersede(self, c: Supersede) -> Draft:
        row = self._fact(self._resolve(c.fact))
        if row["superseded_seq"] is not None:
            raise Rejected("already_superseded", f"fact {row['id']} is already superseded")
        return Draft("fact.superseded", {"fact_id": row["id"], "entity_id": row["entity_id"]}, [row["entity_id"]])

    def _plan_reveal(self, c: Reveal) -> Draft:
        row = self._fact(self._resolve(c.fact))
        if row["visibility"] != "restricted":
            raise Rejected("fact_is_public", f"fact {row['id']} is public; there is nothing to reveal")
        known = {r[0] for r in self.conn.execute("SELECT knower_id FROM fact_knowers WHERE fact_id = ?", (row["id"],))}
        added: list[str] = []
        for k in c.to:
            k = self._resolve(k)
            self._entity(k, "recipient")
            if k not in known and k not in added:
                added.append(k)
        if not added:
            raise Rejected("already_known", f"everyone listed already knows fact {row['id']}")
        return Draft("fact.revealed", {"fact_id": row["id"], "entity_id": row["entity_id"], "added": added},
                     [row["entity_id"]] + added)

    # -- connections -----------------------------------------------------

    def _link(self, from_id: str, to_id: str, label: str) -> tuple[str, str]:
        if not label.strip():
            raise Rejected("invalid_connection", "label must not be empty")
        a, b = self._resolve(from_id), self._resolve(to_id)
        self._entity(a, "connection source")
        self._entity(b, "connection target")
        return a, b

    def _plan_connect(self, c: Connect) -> Draft:
        a, b = self._link(c.from_id, c.to_id, c.label)
        self._json(c.data, "data")
        if self.conn.execute(
            "SELECT 1 FROM connections WHERE from_id = ? AND to_id = ? AND label = ?", (a, b, c.label)
        ).fetchone():
            raise Rejected("duplicate_connection", f"{a} -> {b} ({c.label}) already exists")
        return Draft("connection.added", {"from_id": a, "to_id": b, "label": c.label, "data": c.data}, [a, b])

    def _plan_disconnect(self, c: Disconnect) -> Draft:
        a, b = self._link(c.from_id, c.to_id, c.label)
        if not self.conn.execute(
            "SELECT 1 FROM connections WHERE from_id = ? AND to_id = ? AND label = ?", (a, b, c.label)
        ).fetchone():
            raise Rejected("unknown_connection", f"{a} -> {b} ({c.label}) does not exist")
        return Draft("connection.removed", {"from_id": a, "to_id": b, "label": c.label}, [a, b])

    # -- log-only --------------------------------------------------------

    def _plan_record(self, c: Record) -> Draft:
        if not c.kind.strip():
            raise Rejected("invalid_record", "kind must not be empty")
        if c.kind.startswith(RESERVED_KIND_PREFIXES):
            raise Rejected("reserved_kind", f"kinds starting with {RESERVED_KIND_PREFIXES} are used for state changes")
        self._json(c.payload, "payload")
        touched = []
        for e in c.entities:
            e = self._resolve(e)
            if not self._exists(e):
                raise Rejected("unknown_entity", f"entity {e!r} does not exist")
            touched.append(e)
        return Draft(c.kind, c.payload, touched)
