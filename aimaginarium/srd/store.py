"""Build and query the SRD database (see ``data/srd/SOURCE.md`` for the data)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Union

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "srd"
DEFAULT_DB_PATH = _REPO_ROOT / "data" / "srd.sqlite"
DEFAULT_EDITION = "2024"

_FILE_PREFIX = "5e-SRD-"

_SCHEMA = """
CREATE TABLE srd_records (
    edition    TEXT NOT NULL,
    collection TEXT NOT NULL,
    idx        TEXT NOT NULL,
    name       TEXT,
    url        TEXT NOT NULL,
    data       TEXT NOT NULL CHECK (json_valid(data)),
    PRIMARY KEY (edition, collection, idx)
);
CREATE UNIQUE INDEX srd_records_url ON srd_records (url);
CREATE INDEX srd_records_name ON srd_records (edition, collection, name);
"""


def _collection_name(path: Path) -> str:
    """``5e-SRD-Ability-Scores.json`` -> ``ability-scores``."""
    stem = path.stem
    if stem.startswith(_FILE_PREFIX):
        stem = stem[len(_FILE_PREFIX):]
    return stem.lower()


def build_database(
    db_path: Union[str, os.PathLike] = DEFAULT_DB_PATH,
    data_dir: Union[str, os.PathLike] = DEFAULT_DATA_DIR,
    edition: str = DEFAULT_EDITION,
) -> dict[str, int]:
    """Build a fresh database from the vendored JSON and return record counts.

    The database is written to a temporary file and moved into place, so a
    failed build never leaves a half-written database behind.
    """
    db_path = Path(db_path)
    files = sorted((Path(data_dir) / edition).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no SRD JSON files in {Path(data_dir) / edition}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)

    counts: dict[str, int] = {}
    conn = sqlite3.connect(tmp_path)
    try:
        conn.executescript(_SCHEMA)
        with conn:
            for path in files:
                collection = _collection_name(path)
                records = json.loads(path.read_text(encoding="utf-8"))
                conn.executemany(
                    "INSERT INTO srd_records "
                    "(edition, collection, idx, name, url, data) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            edition,
                            collection,
                            record["index"],
                            record.get("name"),
                            record["url"],
                            json.dumps(record, ensure_ascii=False),
                        )
                        for record in records
                    ],
                )
                counts[collection] = len(records)
    except BaseException:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp_path, db_path)
    return counts


def open_readonly(db_path: Union[str, os.PathLike] = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the built database read-only."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; build it with: python -m aimaginarium.srd build"
        )
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def collections(conn: sqlite3.Connection, edition: str = DEFAULT_EDITION) -> dict[str, int]:
    """Collection names with record counts."""
    rows = conn.execute(
        "SELECT collection, COUNT(*) FROM srd_records WHERE edition = ? "
        "GROUP BY collection ORDER BY collection",
        (edition,),
    )
    return dict(rows)


def get(
    conn: sqlite3.Connection,
    collection: str,
    index: str,
    edition: str = DEFAULT_EDITION,
) -> dict[str, Any] | None:
    """One record by collection and index (for example ``spells``, ``fireball``)."""
    row = conn.execute(
        "SELECT data FROM srd_records WHERE edition = ? AND collection = ? AND idx = ?",
        (edition, collection, index),
    ).fetchone()
    return json.loads(row[0]) if row else None


def list_records(
    conn: sqlite3.Connection,
    collection: str,
    edition: str = DEFAULT_EDITION,
) -> list[dict[str, Any]]:
    """Every record in a collection, ordered by name (for item and spell lists)."""
    rows = conn.execute(
        "SELECT data FROM srd_records WHERE edition = ? AND collection = ? "
        "ORDER BY name, idx",
        (edition, collection),
    )
    return [json.loads(row[0]) for row in rows]


def resolve(conn: sqlite3.Connection, ref: Union[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Follow a cross-reference to its full record.

    ``ref`` is either a URL string or a reference object (``{"index", "name",
    "url"}``). Records are matched on their own ``url`` field, which also covers
    nested records such as ``/api/2024/classes/fighter/levels/3``.
    """
    url = ref["url"] if isinstance(ref, dict) else ref
    row = conn.execute("SELECT data FROM srd_records WHERE url = ?", (url,)).fetchone()
    return json.loads(row[0]) if row else None
