"""Read-only SRD rules data stored in SQLite.

Build the database once with ``python -m aimaginarium.srd build`` and open it
read-only with :func:`open_readonly`. The SRD is rules reference data, kept
apart from world state: the engine's state store never writes to it.
"""

from .store import (
    DEFAULT_DATA_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_EDITION,
    build_database,
    collections,
    get,
    list_records,
    open_readonly,
    resolve,
)

__all__ = [
    "DEFAULT_DATA_DIR",
    "DEFAULT_DB_PATH",
    "DEFAULT_EDITION",
    "build_database",
    "collections",
    "get",
    "list_records",
    "open_readonly",
    "resolve",
]
