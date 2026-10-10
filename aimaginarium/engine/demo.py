"""A tiny hand-made world for trying the engine."""

from __future__ import annotations

from ..world import Connect, Create, Establish, WorldStore

PLAYER_ID = "char-1"


def create_demo_world(store: WorldStore) -> str:
    """Fills an empty store with a tavern, a square, a hero and an innkeeper.

    Args:
        store: An empty world store.

    Returns:
        The player character's entity id.
    """
    store.commit(
        [
            Create(kind="location", name="The Rusty Flagon", ref="@tavern",
                   data={"description": "A low-beamed tavern that smells of smoke and spilled ale."}),
            Create(kind="location", name="Market Square", ref="@square",
                   data={"description": "A cobbled square; stalls are being packed away as dusk falls."}),
            Connect(from_id="@tavern", to_id="@square", label="front door"),
            Connect(from_id="@square", to_id="@tavern", label="tavern door"),
            Create(kind="character", name="Kael", parent_id="@tavern", ref="@kael",
                   data={"player": True, "description": "A road-weary former soldier.",
                         "sheet": {
                             "race": "Human", "class": "Fighter", "level": 3, "background": "Soldier",
                             "alignment": "Neutral Good", "ac": 16, "proficiency": 2, "hp": 24, "max_hp": 24,
                             "xp": 900, "xp_next": 2700,
                             "abilities": {"str": 16, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8},
                             "skills": {"stealth": 1, "persuasion": 0, "athletics": 3, "perception": 2},
                             "proficiencies": ["Light armor", "Medium armor", "Heavy armor", "Shields", "Simple weapons",
                                               "Martial weapons", "Saving throws: STR, CON"],
                             "features": ["Fighting Style: Defense", "Second Wind", "Action Surge"]}}),
            Create(kind="item", name="Shortsword", parent_id="@kael"),
            Create(kind="item", name="Coin purse", parent_id="@kael", data={"description": "Twelve silver pieces."}),
            Create(kind="character", name="Marta", parent_id="@tavern", ref="@marta",
                   data={"description": "The innkeeper, wiping the same mug for the third time."}),
            Establish(entity="@marta", text="Heard wolves too large to be wolves in the northern woods", known_by=["@marta"]),
            Create(kind="item", name="Rusty key", parent_id="@tavern", ref="@key",
                   data={"description": "On a nail behind the bar."}),
        ],
        actor="system",
    )
    return PLAYER_ID
