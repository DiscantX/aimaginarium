"""SQLite schema for the world store.

State tables hold the current world and can be rebuilt from the log. The log
tables are append-only, enforced by triggers.
"""

SCHEMA_VERSION = 1

STATE_SCHEMA = """
CREATE TABLE entities (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   TEXT REFERENCES entities (id),
    data        TEXT NOT NULL CHECK (json_valid(data)),
    created_seq INTEGER NOT NULL,
    updated_seq INTEGER NOT NULL,
    removed_seq INTEGER
);
CREATE INDEX entities_parent ON entities (parent_id);
CREATE INDEX entities_kind_name ON entities (kind, name);

CREATE TABLE connections (
    from_id TEXT NOT NULL REFERENCES entities (id),
    to_id   TEXT NOT NULL REFERENCES entities (id),
    label   TEXT NOT NULL,
    data    TEXT NOT NULL CHECK (json_valid(data)),
    PRIMARY KEY (from_id, to_id, label)
);
CREATE INDEX connections_to ON connections (to_id);

CREATE TABLE facts (
    id             TEXT PRIMARY KEY,
    entity_id      TEXT NOT NULL REFERENCES entities (id),
    text           TEXT NOT NULL,
    visibility     TEXT NOT NULL CHECK (visibility IN ('public', 'restricted')),
    created_seq    INTEGER NOT NULL,
    superseded_seq INTEGER
);
CREATE INDEX facts_entity ON facts (entity_id);

CREATE TABLE fact_knowers (
    fact_id   TEXT NOT NULL REFERENCES facts (id),
    knower_id TEXT NOT NULL REFERENCES entities (id),
    event_seq INTEGER NOT NULL,
    PRIMARY KEY (fact_id, knower_id)
);
CREATE INDEX fact_knowers_knower ON fact_knowers (knower_id);
"""

LOG_SCHEMA = """
CREATE TABLE events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id    INTEGER,
    actor_id   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    world_time INTEGER,
    payload    TEXT NOT NULL CHECK (json_valid(payload)),
    created_at TEXT NOT NULL
);
CREATE INDEX events_kind ON events (kind);
CREATE INDEX events_actor ON events (actor_id);
CREATE INDEX events_turn ON events (turn_id);

CREATE TABLE event_causes (
    event_seq INTEGER NOT NULL REFERENCES events (seq),
    cause_seq INTEGER NOT NULL REFERENCES events (seq),
    PRIMARY KEY (event_seq, cause_seq)
);
CREATE INDEX event_causes_cause ON event_causes (cause_seq);

CREATE TABLE event_entities (
    event_seq INTEGER NOT NULL REFERENCES events (seq),
    entity_id TEXT NOT NULL,
    PRIMARY KEY (event_seq, entity_id)
);
CREATE INDEX event_entities_entity ON event_entities (entity_id);

CREATE TABLE counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER event_causes_no_update BEFORE UPDATE ON event_causes
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER event_causes_no_delete BEFORE DELETE ON event_causes
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER event_entities_no_update BEFORE UPDATE ON event_entities
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER event_entities_no_delete BEFORE DELETE ON event_entities
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
"""
