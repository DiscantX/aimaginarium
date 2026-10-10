"""A character as a client shows it: everything the viewer may know, in one structure.

Presentation data shared by every client. Every field is optional, because what is known about a character grows
over time (spells, features, ...) and differs by viewer: the API sends a projection, never more than the viewer's
own character knows. :func:`character_from_dict` reads that projection; fields missing from it stay empty and the
panel leaves those sections out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from .party import Controller, PartyMember

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
COINS = ("pp", "gp", "ep", "sp", "cp")


def modifier(score: int) -> int:
    """The 5e ability modifier of a score."""
    return (score - 10) // 2


def signed(number: int) -> str:
    """``+2``, ``-1`` and ``+0``."""
    return f"{number:+d}"


@dataclass(frozen=True)
class Item:
    """One carried item.

    Attributes:
        name: What the character calls it.
        description: Optional short description.
    """

    name: str
    description: str = ""


@dataclass(frozen=True)
class CharacterView:
    """What a viewer may know about one character.

    Attributes:
        name: Display name.
        race: Race or species.
        class_name: Class, e.g. ``"Fighter"``.
        level: Character level.
        background: Background.
        alignment: Alignment.
        description: Prose description.
        ac: Armor class.
        proficiency: Proficiency bonus.
        inspiration: Whether the character has inspiration.
        hp: Current hit points.
        max_hp: Maximum hit points.
        temp_hp: Temporary hit points.
        xp: Experience points.
        xp_next: Experience needed for the next level.
        abilities: Ability scores by lower-case abbreviation (``str``, ``dex``, ...).
        skills: Skill bonuses by name.
        proficiencies: Armor, weapon, tool, language and saving-throw proficiencies.
        equipment: What is worn or wielded.
        inventory: What is carried.
        coins: Coins by type (``pp``, ``gp``, ``ep``, ``sp``, ``cp``).
        features: Class, race and background features.
        spells: Spells known or prepared.
        statuses: Conditions and effects.
        facts: Facts the viewer's character knows about this one.
        controller: Who plays this character.
        mine: Whether the viewer controls this character.
    """

    name: str
    race: str = ""
    class_name: str = ""
    level: int | None = None
    background: str = ""
    alignment: str = ""
    description: str = ""
    ac: int | None = None
    proficiency: int | None = None
    inspiration: bool = False
    hp: int | None = None
    max_hp: int | None = None
    temp_hp: int = 0
    xp: int | None = None
    xp_next: int | None = None
    abilities: dict[str, int] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    proficiencies: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    inventory: tuple[Item, ...] = ()
    coins: dict[str, int] = field(default_factory=dict)
    features: tuple[str, ...] = ()
    spells: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    controller: Controller = Controller.HUMAN
    mine: bool = False

    @property
    def identity(self) -> str:
        """``"Human · Fighter 3 · Soldier · Neutral Good"``, with whatever is known."""
        klass = f"{self.class_name} {self.level}".strip() if self.class_name else (f"Level {self.level}" if self.level else "")
        return " · ".join(part for part in (self.race, klass, self.background, self.alignment) if part)

    @property
    def hp_fraction(self) -> float | None:
        """Share of hit points left (0 to 1), or ``None`` when not known."""
        if self.hp is None or not self.max_hp:
            return None
        return max(0.0, min(1.0, self.hp / self.max_hp))


def _items(raw: Iterable[Any]) -> tuple[Item, ...]:
    return tuple(Item(i, "") if isinstance(i, str) else Item(i.get("name", "?"), i.get("description", "")) for i in raw)


def character_from_dict(data: dict[str, Any], carrying: Iterable[Any] = (), mine: bool = False) -> CharacterView:
    """Reads a character projection (the ``character`` part of a player view, or a party entry's ``character``).

    Args:
        data: The character: ``name``, ``description``, ``facts``, ``skills`` and any of the optional sheet keys
            (``race``, ``class``, ``level``, ``background``, ``alignment``, ``ac``, ``proficiency``, ``inspiration``,
            ``hp``, ``max_hp``, ``temp_hp``, ``xp``, ``xp_next``, ``abilities``, ``proficiencies``, ``equipment``,
            ``coins``, ``features``, ``spells``, ``statuses``, ``controller``).
        carrying: The items carried (dicts with ``name`` and ``description``, or plain names).
        mine: Whether the viewer controls this character.
    """
    return CharacterView(
        name=data.get("name", "?"), race=data.get("race", ""), class_name=data.get("class", ""), level=data.get("level"),
        background=data.get("background", ""), alignment=data.get("alignment", ""), description=data.get("description", ""),
        ac=data.get("ac"), proficiency=data.get("proficiency"), inspiration=bool(data.get("inspiration", False)),
        hp=data.get("hp"), max_hp=data.get("max_hp"), temp_hp=data.get("temp_hp", 0), xp=data.get("xp"),
        xp_next=data.get("xp_next"), abilities=dict(data.get("abilities", {})), skills=dict(data.get("skills", {})),
        proficiencies=tuple(data.get("proficiencies", ())), equipment=tuple(data.get("equipment", ())),
        inventory=_items(carrying), coins=dict(data.get("coins", {})), features=tuple(data.get("features", ())),
        spells=tuple(data.get("spells", ())), statuses=tuple(data.get("statuses", ())), facts=tuple(data.get("facts", ())),
        controller=Controller(data.get("controller", Controller.HUMAN)), mine=mine,
    )


def character_from_member(member: PartyMember) -> CharacterView:
    """The little a party card knows, as a character (used when the API sends nothing more about a member)."""
    return CharacterView(name=member.name, class_name=member.class_name, level=member.level, hp=member.hp,
                         max_hp=member.max_hp, statuses=member.statuses, controller=member.controller, mine=member.mine)


def characters_from_view(view: dict[str, Any], members: list[PartyMember]) -> dict[str, CharacterView]:
    """Builds the character of every party member from a player view, by member id.

    A view without a ``party`` list describes only the player's own character. In a ``party`` list each entry may
    carry a ``character`` projection; members without one fall back to what their card knows.
    """
    if view.get("party"):
        out = {}
        for raw, member in zip(view["party"], members):
            if raw.get("character"):
                out[member.id] = character_from_dict(raw["character"], raw.get("carrying", ()), member.mine)
            else:
                out[member.id] = character_from_member(member)
        return out
    if not members:
        return {}
    return {members[0].id: character_from_dict(view.get("character") or {}, view.get("carrying", ()), mine=True)}


_RACES = ("Human", "Elf", "Dwarf", "Halfling", "Gnome", "Half-Orc", "Tiefling")
_BACKGROUNDS = ("Acolyte", "Criminal", "Folk Hero", "Sage", "Soldier", "Outlander")
_ALIGNMENTS = ("Lawful Good", "Neutral Good", "Chaotic Good", "True Neutral", "Chaotic Neutral", "Lawful Neutral")
_CASTERS = {"Wizard", "Cleric", "Bard", "Paladin", "Ranger"}
_SKILLS = ("acrobatics", "arcana", "athletics", "insight", "medicine", "perception", "persuasion", "stealth")


def demo_character(member: PartyMember) -> CharacterView:
    """A made-up full sheet for a stand-in member (dev only), the same every time for the same member.

    Args:
        member: The stand-in party member; its card fields are kept.
    """
    rng = random.Random(member.id)
    scores = {a: rng.randint(8, 17) for a in ABILITIES}
    prof = 2 + ((member.level or 1) - 1) // 4
    spells = ("Cure Wounds", "Guiding Bolt", "Shield of Faith", "Detect Magic") if member.class_name in _CASTERS else ()
    return CharacterView(
        name=member.name, race=rng.choice(_RACES), class_name=member.class_name, level=member.level,
        background=rng.choice(_BACKGROUNDS), alignment=rng.choice(_ALIGNMENTS),
        description=f"{member.name} travels with the party, watchful and quick to speak up.",
        ac=rng.randint(12, 18), proficiency=prof, inspiration=rng.random() < 0.3, hp=member.hp, max_hp=member.max_hp,
        temp_hp=rng.choice((0, 0, 3)), xp=rng.randint(300, 2000), xp_next=2700, abilities=scores,
        skills={s: modifier(scores[a]) + prof for s, a in zip(_SKILLS[:5], ("dex", "int", "str", "wis", "wis"))},
        proficiencies=("Simple weapons", "Light armor", "Common", "Thieves' tools"),
        equipment=("Longsword", "Chain shirt"), inventory=(Item("Rope, 50 ft"), Item("Healing potion", "Red and fizzing."),
                                                          Item("Waterskin")),
        coins={"gp": rng.randint(0, 90), "sp": rng.randint(0, 40), "cp": rng.randint(0, 99)},
        features=("Second Wind", "Darkvision"), spells=spells, statuses=member.statuses,
        facts=("Met at the Rusty Flagon.",), controller=member.controller, mine=member.mine,
    )
