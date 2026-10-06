"""Apply one event's payload to the state tables.

This is the only code that writes state, and it reads nothing but the event
payload. Live commits and log replay both go through it, which is what makes
the replay check meaningful.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import paths


def dumps(value: Any) -> str:
    """Canonical JSON; raises ValueError/TypeError for values JSON cannot hold."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def apply_event(conn: sqlite3.Connection, seq: int, kind: str, payload: dict[str, Any]) -> None:
    handler = _HANDLERS.get(kind)
    if handler is not None:
        handler(conn, seq, payload)
    elif kind.startswith(("entity.", "fact.", "connection.")):
        raise ValueError(f"unknown state event kind {kind!r}")
    # anything else is a log-only record and changes no state


def _created(conn, seq, p):
    conn.execute(
        "INSERT INTO entities (id, kind, name, parent_id, data, created_seq, updated_seq) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (p["id"], p["kind"], p["name"], p["parent_id"], dumps(p["data"]), seq, seq),
    )


def _updated(conn, seq, p):
    row = conn.execute("SELECT name, data FROM entities WHERE id = ?", (p["id"],)).fetchone()
    data = json.loads(row[1])
    for change in p.get("changes", []):
        segments = change["path"].split(".")
        if change["op"] == "set":
            paths.set_value(data, segments, change["new"])
        else:
            paths.unset_value(data, segments)
    name = p["name"]["new"] if "name" in p else row[0]
    conn.execute(
        "UPDATE entities SET name = ?, data = ?, updated_seq = ? WHERE id = ?",
        (name, dumps(data), seq, p["id"]),
    )


def _moved(conn, seq, p):
    conn.execute("UPDATE entities SET parent_id = ?, updated_seq = ? WHERE id = ?", (p["to"], seq, p["id"]))


def _removed(conn, seq, p):
    for c in p.get("connections_removed", []):
        conn.execute(
            "DELETE FROM connections WHERE from_id = ? AND to_id = ? AND label = ?",
            (c["from_id"], c["to_id"], c["label"]),
        )
    conn.execute("UPDATE entities SET removed_seq = ?, updated_seq = ? WHERE id = ?", (seq, seq, p["id"]))


def _fact_established(conn, seq, p):
    conn.execute(
        "INSERT INTO facts (id, entity_id, text, visibility, created_seq) VALUES (?, ?, ?, ?, ?)",
        (p["fact_id"], p["entity_id"], p["text"], p["visibility"], seq),
    )
    for knower in p.get("known_by") or []:
        conn.execute(
            "INSERT INTO fact_knowers (fact_id, knower_id, event_seq) VALUES (?, ?, ?)",
            (p["fact_id"], knower, seq),
        )


def _fact_superseded(conn, seq, p):
    conn.execute("UPDATE facts SET superseded_seq = ? WHERE id = ?", (seq, p["fact_id"]))


def _fact_revealed(conn, seq, p):
    for knower in p["added"]:
        conn.execute(
            "INSERT INTO fact_knowers (fact_id, knower_id, event_seq) VALUES (?, ?, ?)",
            (p["fact_id"], knower, seq),
        )


def _connection_added(conn, seq, p):
    conn.execute(
        "INSERT INTO connections (from_id, to_id, label, data) VALUES (?, ?, ?, ?)",
        (p["from_id"], p["to_id"], p["label"], dumps(p.get("data", {}))),
    )


def _connection_removed(conn, seq, p):
    conn.execute(
        "DELETE FROM connections WHERE from_id = ? AND to_id = ? AND label = ?",
        (p["from_id"], p["to_id"], p["label"]),
    )


_HANDLERS = {
    "entity.created": _created,
    "entity.updated": _updated,
    "entity.moved": _moved,
    "entity.removed": _removed,
    "fact.established": _fact_established,
    "fact.superseded": _fact_superseded,
    "fact.revealed": _fact_revealed,
    "connection.added": _connection_added,
    "connection.removed": _connection_removed,
}
