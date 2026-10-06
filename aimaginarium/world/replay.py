"""Check that the state tables are exactly what the event log says they should be."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .apply import apply_event
from .schema import STATE_SCHEMA
from .store import WorldStore

_TABLES = {
    "entities": "id",
    "connections": "from_id, to_id, label",
    "facts": "id",
    "fact_knowers": "fact_id, knower_id",
}


def snapshot(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for table, order in _TABLES.items():
        rows = []
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            record = dict(row)
            if "data" in record:
                record["data"] = json.loads(record["data"])
            rows.append(record)
        result[table] = rows
    return result


def replay_snapshot(store: WorldStore) -> dict[str, list[dict[str, Any]]]:
    """Rebuild the state in memory from the log alone."""
    mem = sqlite3.connect(":memory:", isolation_level=None)
    mem.row_factory = sqlite3.Row
    mem.execute("PRAGMA foreign_keys = ON")
    mem.executescript(STATE_SCHEMA)
    try:
        for event in store.events():
            apply_event(mem, event.seq, event.kind, event.payload)
        return snapshot(mem)
    finally:
        mem.close()


def verify_replay(store: WorldStore) -> list[str]:
    """Differences between the live state and the state rebuilt from the log (empty when they match)."""
    live = snapshot(store.connection)
    rebuilt = replay_snapshot(store)
    problems: list[str] = []
    for table in _TABLES:
        if live[table] != rebuilt[table]:
            live_ids = {json.dumps(r, sort_keys=True) for r in live[table]}
            rebuilt_ids = {json.dumps(r, sort_keys=True) for r in rebuilt[table]}
            for row in sorted(live_ids - rebuilt_ids):
                problems.append(f"{table}: live only: {row}")
            for row in sorted(rebuilt_ids - live_ids):
                problems.append(f"{table}: replay only: {row}")
    return problems
