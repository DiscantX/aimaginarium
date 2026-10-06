import sqlite3

import pytest

from aimaginarium.world import (
    CommitError, Connect, Create, Disconnect, Establish, Move, Record, Remove, Reveal, Supersede, Update,
    WorldStore, parse_changes, verify_replay,
)


@pytest.fixture()
def store():
    with WorldStore.open() as s:
        yield s


@pytest.fixture()
def tavern(store):
    """The Sunken Lantern with Aldric, his longsword, and the street outside."""
    store.commit(
        [
            Create(kind="location", name="The Sunken Lantern", ref="@tavern",
                   data={"description": "A low-ceilinged tavern."}),
            Create(kind="location", name="Mill Street", ref="@street"),
            Connect(from_id="@tavern", to_id="@street", label="front door"),
            Create(kind="character", name="Aldric", parent_id="@tavern", ref="@aldric",
                   data={"player": True, "sheet": {"class": "fighter", "hp": {"current": 28, "max": 28}}}),
            Create(kind="item", name="Longsword", parent_id="@aldric", data={"srd": "equipment/longsword", "quantity": 1}),
            Create(kind="item", name="Rusty key", parent_id="@tavern"),
        ],
        actor="system",
    )
    return store


def rejected(store, changes, code, **kwargs):
    with pytest.raises(CommitError) as info:
        store.commit(changes, actor="system", **kwargs)
    assert info.value.errors[0].code == code, info.value.errors
    return info.value


# -- entities ---------------------------------------------------------------


def test_scene_is_created_with_readable_ids(tavern):
    assert [e.id for e in tavern.find(kind="location")] == ["loc-1", "loc-2"]
    aldric = tavern.get_entity("char-1")
    assert aldric.parent_id == "loc-1" and aldric.data["sheet"]["hp"]["current"] == 28
    assert [e.name for e in tavern.children("char-1")] == ["Longsword"]
    assert tavern.location_of("item-1") == "loc-1"
    assert tavern.ancestors("item-1") == ["char-1", "loc-1"]
    assert [c["to_id"] for c in tavern.connections("loc-1")] == ["loc-2"]
    assert tavern.find(name="aldric")[0].id == "char-1"


def test_update_records_old_and_new_values(tavern):
    result = tavern.commit([Update(entity="char-1", set={"sheet.hp.current": 20, "sheet.conditions.poisoned": True},
                                   unset=["player"])], actor="npc-ogre")
    changes = {c["path"]: c for c in result.events[0].payload["changes"]}
    assert changes["sheet.hp.current"]["old"] == 28 and changes["sheet.hp.current"]["new"] == 20
    assert "old" not in changes["sheet.conditions.poisoned"]
    assert changes["player"]["op"] == "unset" and changes["player"]["old"] is True
    aldric = tavern.get_entity("char-1")
    assert aldric.data["sheet"]["hp"]["current"] == 20 and "player" not in aldric.data
    assert aldric.data["sheet"]["conditions"] == {"poisoned": True}


def test_update_rejections(tavern):
    rejected(tavern, [Update(entity="char-99", set={"a": 1})], "unknown_entity")
    rejected(tavern, [Update(entity="char-1")], "empty_update")
    rejected(tavern, [Update(entity="char-1", set={"established": []})], "reserved_path")
    rejected(tavern, [Update(entity="char-1", set={"sheet.class.sub": 1})], "path_blocked")
    rejected(tavern, [Update(entity="char-1", unset=["sheet.nope"])], "path_missing")
    rejected(tavern, [Update(entity="char-1", set={"a..b": 1})], "invalid_path")
    rejected(tavern, [Update(entity="char-1", set={"x": float("nan")})], "invalid_json")


def test_create_rejections(tavern):
    rejected(tavern, [Create(kind="item", name="Orb", parent_id="loc-99")], "unknown_entity")
    rejected(tavern, [Create(kind="item", name=" ")], "invalid_entity")
    rejected(tavern, [Create(kind="item", name="Orb", id="item-1")], "duplicate_id")
    rejected(tavern, [Create(kind="item", name="Orb", id="Bad Id")], "invalid_id")
    rejected(tavern, [Create(kind="item", name="Orb", data={"established": []})], "reserved_path")


def test_move_picks_up_an_item_and_rejects_cycles(tavern):
    tavern.commit([Move(entity="item-2", to="char-1")], actor="char-1")
    assert tavern.get_entity("item-2").parent_id == "char-1"
    assert tavern.children("loc-1", kind="item") == []
    rejected(tavern, [Move(entity="loc-1", to="item-1")], "containment_cycle")
    rejected(tavern, [Move(entity="item-2", to="char-1")], "no_change")
    rejected(tavern, [Move(entity="item-2", to="loc-99")], "unknown_entity")


def test_remove_is_soft_and_checks_children_and_connections(tavern):
    rejected(tavern, [Remove(entity="char-1")], "has_children")
    tavern.commit([Remove(entity="item-1")], actor="system")
    assert tavern.get_entity("item-1") is None
    assert tavern.get_entity("item-1", include_removed=True).removed_seq is not None
    assert tavern.children("char-1") == []
    rejected(tavern, [Move(entity="item-1", to="loc-1")], "removed_entity")
    # removing a location drops its connections, recording them in the event
    tavern.commit([Remove(entity="item-2")], actor="system")
    tavern.commit([Remove(entity="char-1")], actor="system")
    result = tavern.commit([Remove(entity="loc-1")], actor="system")
    assert result.events[0].payload["connections_removed"][0]["label"] == "front door"
    assert tavern.connections("loc-1") == []


def test_connections(tavern):
    rejected(tavern, [Connect(from_id="loc-1", to_id="loc-2", label="front door")], "duplicate_connection")
    tavern.commit([Connect(from_id="loc-2", to_id="loc-1", label="tavern door"),
                   Disconnect(from_id="loc-1", to_id="loc-2", label="front door")], actor="system")
    assert [c["label"] for c in tavern.connections("loc-2")] == ["tavern door"]
    rejected(tavern, [Disconnect(from_id="loc-1", to_id="loc-2", label="front door")], "unknown_connection")


# -- facts ------------------------------------------------------------------


def test_established_facts_public_and_restricted(tavern):
    result = tavern.commit(
        [Create(kind="character", name="Marta", parent_id="loc-1", ref="@marta"),
         Establish(entity="@marta", text="Burn scar across her left hand"),
         Establish(entity="@marta", text="Reports to the Thieves' Guild", known_by=[], ref="@secret")],
        actor="system",
    )
    marta = tavern.get_entity("char-2")
    assert [f.text for f in marta.established] == ["Burn scar across her left hand", "Reports to the Thieves' Guild"]
    public, secret = marta.established
    assert public.visibility == "public" and public.known_by is None
    assert secret.visibility == "restricted" and secret.known_by == ()
    assert result.refs["@secret"] == secret.id
    assert tavern.get_fact(secret.id).entity_id == "char-2"


def test_many_unrelated_characters_can_learn_the_same_secret(tavern):
    tavern.commit([Create(kind="character", name="Marta", parent_id="loc-1"),
                   Establish(entity="char-2", text="A beast haunts the old wood", known_by=["char-2"])],
                  actor="system")
    fact = tavern.facts("char-2")[0]
    travellers = []
    for i in range(50):
        r = tavern.commit([Create(kind="character", name=f"Traveller {i}", parent_id="loc-2")], actor="system")
        travellers.append(r.events[0].payload["id"])
    before = tavern.get_event(tavern.events()[-1].seq).seq
    for who in travellers:
        tavern.commit([Reveal(fact=fact.id, to=[who])], actor="char-2", causes=[before])
    assert len(tavern.knowers(fact.id)) == 51
    assert tavern.knowers(fact.id)[0] == "char-2"
    assert [f.id for f in tavern.known_facts(travellers[7])] == [fact.id]
    assert tavern.get_fact(fact.id).known_by[-1] == travellers[-1]


def test_reveal_rejections(tavern):
    tavern.commit([Establish(entity="char-1", text="Public thing"),
                   Establish(entity="char-1", text="Hidden thing", known_by=["char-1"])], actor="system")
    rejected(tavern, [Reveal(fact="f-1", to=["char-1"])], "fact_is_public")
    rejected(tavern, [Reveal(fact="f-2", to=["char-1"])], "already_known")
    rejected(tavern, [Reveal(fact="f-2", to=["char-99"])], "unknown_entity")
    rejected(tavern, [Reveal(fact="f-99", to=["char-1"])], "unknown_fact")


def test_supersede_keeps_history(tavern):
    tavern.commit([Establish(entity="item-1", text="Nicked along the edge")], actor="system")
    result = tavern.commit([Supersede(fact="f-1"), Establish(entity="item-1", text="Freshly reforged")], actor="system")
    assert [f.text for f in tavern.facts("item-1")] == ["Freshly reforged"]
    both = tavern.facts("item-1", include_superseded=True)
    assert both[0].superseded_seq == result.events[0].seq
    assert [f.text for f in tavern.get_entity("item-1").established] == ["Freshly reforged"]
    rejected(tavern, [Supersede(fact="f-1")], "already_superseded")


# -- log, causes, atomicity -------------------------------------------------


def test_attack_is_a_roll_then_a_caused_update(tavern):
    tavern.commit([Create(kind="character", name="Ogre", parent_id="loc-1", data={"hp": {"current": 15}})], actor="system")
    turn = tavern.new_turn()
    roll = tavern.commit([Record(kind="roll", entities=["char-2"],
                                 payload={"purpose": "attack", "dice": "1d20", "rolled": 13, "total": 18})],
                         actor="system", turn=turn, world_time=86400).events[0]
    hit = tavern.commit([Update(entity="char-2", set={"hp.current": 8})], actor="char-1", turn=turn,
                        causes=[roll.seq], world_time=86400).events[0]
    assert hit.causes == (roll.seq,) and hit.turn_id == turn and hit.world_time == 86400
    assert [e.seq for e in tavern.causal_chain(hit.seq)] == [roll.seq]
    assert [e.kind for e in tavern.events(turn=turn)] == ["roll", "entity.updated"]
    assert roll.seq in [e.seq for e in tavern.events(entity="char-2")]
    assert [e.kind for e in tavern.events(kind="roll")] == ["roll"]
    assert [e.seq for e in tavern.events(actor="char-1")] == [hit.seq]


def test_causal_chain_is_transitive(store):
    a = store.commit([Record(kind="note")], actor="system").events[0]
    b = store.commit([Record(kind="note")], actor="system", causes=[a.seq]).events[0]
    c = store.commit([Record(kind="note")], actor="system", causes=[b.seq]).events[0]
    assert [e.seq for e in store.causal_chain(c.seq)] == [a.seq, b.seq]
    rejected(store, [Record(kind="note")], "unknown_cause", causes=[999])


def test_record_rules(tavern):
    rejected(tavern, [Record(kind="entity.created")], "reserved_kind")
    rejected(tavern, [Record(kind="roll", entities=["char-99"])], "unknown_entity")
    rejected(tavern, [Record(kind=" ")], "invalid_record")


def test_failed_commit_writes_nothing(tavern):
    events_before = len(tavern.events())
    with pytest.raises(CommitError) as info:
        tavern.commit([Create(kind="item", name="Ghost coin"), Update(entity="char-99", set={"a": 1})], actor="system")
    assert info.value.errors[0].index == 1
    assert info.value.to_dict()["errors"][0]["code"] == "unknown_entity"
    assert len(tavern.events()) == events_before
    assert tavern.find(name="Ghost coin") == []
    # the id counter rolled back too
    created = tavern.commit([Create(kind="item", name="Real coin")], actor="system").events[0]
    assert created.payload["id"] == "item-3"


def test_refs(store):
    rejected(store, [Update(entity="@nope", set={"a": 1})], "unknown_ref")
    rejected(store, [Create(kind="item", name="A", ref="a")], "invalid_ref")
    rejected(store, [Create(kind="item", name="A", ref="@a"), Create(kind="item", name="B", ref="@a")], "duplicate_ref")


def test_actor_and_empty_commit(store):
    with pytest.raises(CommitError) as info:
        store.commit([Record(kind="x")], actor=" ")
    assert info.value.errors[0].code == "invalid_actor"
    with pytest.raises(CommitError) as info:
        store.commit([], actor="system")
    assert info.value.errors[0].code == "empty_commit"


def test_log_is_append_only(tavern):
    first = tavern.events()[0].seq
    tavern.commit([Record(kind="note")], actor="system", causes=[first])  # gives event_causes a row
    with pytest.raises(sqlite3.DatabaseError):
        tavern.connection.execute("UPDATE events SET kind = 'x'")
    with pytest.raises(sqlite3.DatabaseError):
        tavern.connection.execute("DELETE FROM events")
    with pytest.raises(sqlite3.DatabaseError):
        tavern.connection.execute("DELETE FROM event_causes")
    with pytest.raises(sqlite3.DatabaseError):
        tavern.connection.execute("DELETE FROM event_entities")


# -- LLM proposals ----------------------------------------------------------


def test_llm_json_proposal_validates_into_changes(store):
    proposal = [
        {"op": "create", "kind": "character", "name": "Marta", "ref": "@marta"},
        {"op": "establish", "entity": "@marta", "text": "Burn scar", "known_by": None},
        {"op": "update", "entity": "@marta", "set": {"mood": "wary"}},
    ]
    result = store.commit(parse_changes(proposal), actor="director")
    assert [e.kind for e in result.events] == ["entity.created", "fact.established", "entity.updated"]
    # dicts are accepted directly too
    store.commit([{"op": "update", "entity": "char-1", "set": {"mood": "calm"}}], actor="director")
    with pytest.raises(CommitError) as info:
        store.commit([{"op": "teleport", "entity": "char-1"}], actor="director")
    assert info.value.errors[0].code == "invalid_change"
    with pytest.raises(CommitError):
        store.commit([{"op": "update", "entity": "char-1", "set": {"a": 1}, "surprise": True}], actor="director")


# -- replay -----------------------------------------------------------------


def test_replay_matches_live_state_after_a_busy_game(tavern):
    tavern.commit([Establish(entity="item-1", text="Nicked", known_by=["char-1"]),
                   Reveal(fact="f-1", to=["item-2"]),
                   Update(entity="char-1", name="Aldric the Bold", set={"sheet.hp.current": 3}, unset=["player"]),
                   Move(entity="item-2", to="char-1"),
                   Supersede(fact="f-1"),
                   Disconnect(from_id="loc-1", to_id="loc-2", label="front door"),
                   Remove(entity="item-1")], actor="system")
    assert verify_replay(tavern) == []


def test_replay_detects_tampering(tavern):
    tavern.connection.execute("UPDATE entities SET name = 'Impostor' WHERE id = 'char-1'")
    problems = verify_replay(tavern)
    assert problems and any("entities" in p for p in problems)


def test_world_persists_on_disk(tmp_path):
    path = tmp_path / "world.sqlite"
    with WorldStore.open(path) as s:
        s.commit([Create(kind="location", name="Cellar")], actor="system")
    with WorldStore.open(path) as s:
        assert s.get_entity("loc-1").name == "Cellar"
        s.commit([Create(kind="location", name="Attic")], actor="system")
        assert s.get_entity("loc-2").name == "Attic"
        assert verify_replay(s) == []
