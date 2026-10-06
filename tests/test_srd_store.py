import json
import sqlite3

import pytest

from aimaginarium import srd
from aimaginarium.srd.store import DEFAULT_DATA_DIR, DEFAULT_EDITION, _collection_name

SOURCE_FILES = sorted((DEFAULT_DATA_DIR / DEFAULT_EDITION).glob("*.json"))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("srd") / "srd.sqlite"
    counts = srd.build_database(db_path)
    return db_path, counts


@pytest.fixture()
def conn(built):
    db_path, _ = built
    connection = srd.open_readonly(db_path)
    yield connection
    connection.close()


def test_record_counts_match_source_files(built, conn):
    _, counts = built
    expected = {
        _collection_name(path): len(json.loads(path.read_text(encoding="utf-8")))
        for path in SOURCE_FILES
    }
    assert expected, "no vendored SRD files found"
    assert counts == expected
    assert srd.collections(conn) == expected


def _refs(obj, top=True):
    """Yield every nested reference object ({'index', 'url', ...}) in a record."""
    if isinstance(obj, dict):
        if not top and "url" in obj and "index" in obj:
            yield obj
        for value in obj.values():
            yield from _refs(value, top=False)
    elif isinstance(obj, list):
        for value in obj:
            yield from _refs(value, top=False)


def test_every_cross_reference_resolves(conn):
    unresolved = []
    for collection in srd.collections(conn):
        for record in srd.list_records(conn, collection):
            for ref in _refs(record):
                if srd.resolve(conn, ref) is None:
                    unresolved.append((collection, record["index"], ref["url"]))
    assert not unresolved, unresolved[:10]


def test_resolve_by_url_string_and_by_reference_object(conn):
    fireball = srd.get(conn, "spells", "fireball")
    assert fireball["name"] == "Fireball"
    assert srd.resolve(conn, fireball["url"]) == fireball
    assert srd.resolve(conn, {"index": "fireball", "name": "Fireball", "url": fireball["url"]}) == fireball
    # nested record: class levels live under the class's URL
    level = srd.get(conn, "levels", "fighter-3")
    assert srd.resolve(conn, level["url"]) == level
    assert srd.resolve(conn, "/api/2024/spells/not-a-spell") is None


def test_item_and_spell_lists_are_prepopulated(conn):
    items = srd.list_records(conn, "equipment")
    spells = srd.list_records(conn, "spells")
    assert any(item["index"] == "longsword" for item in items)
    assert any(spell["index"] == "fireball" for spell in spells)
    names = [item["name"] for item in items]
    assert names == sorted(names)


def test_database_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM srd_records")


def test_rebuild_replaces_the_database(built, tmp_path):
    db_path = tmp_path / "again.sqlite"
    first = srd.build_database(db_path)
    second = srd.build_database(db_path)
    assert first == second
    assert not db_path.with_name(db_path.name + ".tmp").exists()


def test_open_readonly_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        srd.open_readonly(tmp_path / "missing.sqlite")
