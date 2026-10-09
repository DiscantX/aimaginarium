"""The party as a client shows it: who is in it, who controls each member and what a card displays.

This is presentation data, shared by every client (Textual now, web later). The engine has no party
model yet (what counts as a member is still open), so :func:`party_from_view` builds the party from what
the player view offers, and :func:`demo_party` supplies stand-in members for trying the layout.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

SELF_ID = "self"
"""Id of the player's own character when the view carries no ids (a projection hides them)."""


class Controller(str, Enum):
    """Who plays a party member."""

    HUMAN = "human"
    LLM_MCP = "llm-mcp"
    LLM_INTERNAL = "llm-internal"


@dataclass(frozen=True)
class PartyMember:
    """One card's worth of a character, as the viewer may see it.

    Anything the viewer may not see is simply ``None`` or empty; what is visible of members other than the
    player's own character is decided by the API's projection, not by the client.

    Attributes:
        id: Stable id used for selection.
        name: Display name.
        class_name: Class, e.g. ``"Fighter"`` (empty if unknown).
        level: Character level, if known.
        hp: Current hit points, if known.
        max_hp: Maximum hit points, if known.
        statuses: Short labels of conditions or effects, e.g. ``("poisoned",)``.
        controller: Who plays this member.
        mine: Whether this is the character the viewing player controls.
    """

    id: str
    name: str
    class_name: str = ""
    level: int | None = None
    hp: int | None = None
    max_hp: int | None = None
    statuses: tuple[str, ...] = ()
    controller: Controller = Controller.HUMAN
    mine: bool = False

    @property
    def hp_fraction(self) -> float | None:
        """Share of hit points left (0 to 1), or ``None`` when they are not known."""
        if self.hp is None or not self.max_hp:
            return None
        return max(0.0, min(1.0, self.hp / self.max_hp))

    @property
    def subtitle(self) -> str:
        """``"Fighter 3"``, ``"Fighter"``, ``"Level 3"`` or an empty string."""
        if self.class_name and self.level is not None:
            return f"{self.class_name} {self.level}"
        return self.class_name or (f"Level {self.level}" if self.level is not None else "")


def party_from_view(view: dict[str, Any]) -> list[PartyMember]:
    """Builds the party from a player view.

    A view with a ``party`` list (dicts with :class:`PartyMember` field names) uses it. Otherwise the party
    is the player's own character alone, taken from ``character``; the optional keys ``class``, ``level``,
    ``hp``, ``max_hp`` and ``statuses`` fill the card when the engine provides them.

    Args:
        view: The ``StateView("player")`` data.

    Returns:
        The members in display order, the player's own character marked ``mine``.
    """
    if view.get("party"):
        return [_member(raw, mine=raw.get("mine", False)) for raw in view["party"]]
    character = view.get("character") or {}
    return [_member({"id": SELF_ID, "class_name": character.get("class", ""), **character}, mine=True)]


def _member(raw: dict[str, Any], mine: bool) -> PartyMember:
    return PartyMember(
        id=str(raw.get("id", raw.get("name", ""))),
        name=raw.get("name", "?"),
        class_name=raw.get("class_name", ""),
        level=raw.get("level"),
        hp=raw.get("hp"),
        max_hp=raw.get("max_hp"),
        statuses=tuple(raw.get("statuses", ())),
        controller=Controller(raw.get("controller", Controller.HUMAN)),
        mine=mine,
    )


_DEMO = [
    ("Mira Vael", "Wizard", 3, 14, 20, ("concentrating",), Controller.LLM_MCP),
    ("Torvik", "Cleric", 3, 9, 27, ("poisoned",), Controller.LLM_INTERNAL),
    ("Brannoch", "Barbarian", 3, 33, 33, (), Controller.LLM_INTERNAL),
    ("Pip", "Rogue", 3, 2, 21, ("prone", "frightened"), Controller.LLM_INTERNAL),
    ("Sister Ansel", "Paladin", 3, 28, 30, (), Controller.LLM_MCP),
    ("Gorm", "Ranger", 3, 0, 25, ("unconscious",), Controller.LLM_INTERNAL),
    ("Odalys", "Bard", 3, 18, 18, (), Controller.LLM_INTERNAL),
]


def demo_party(player: PartyMember, size: int = 4) -> list[PartyMember]:
    """Stand-in party for trying the layout (dev only): the player first, then made-up companions.

    Args:
        player: The player's own member, kept as the first card (blank fields are filled with stand-ins).
        size: Total members, 1 to 8.
    """
    companions = [
        PartyMember(id=f"demo-{i}", name=n, class_name=c, level=lv, hp=hp, max_hp=mx, statuses=st, controller=ctl)
        for i, (n, c, lv, hp, mx, st, ctl) in enumerate(_DEMO)
    ]
    player = replace(player, class_name=player.class_name or "Fighter", level=player.level or 3,
                     hp=player.hp if player.hp is not None else 24, max_hp=player.max_hp or 24)
    return [player, *companions[: max(1, min(size, 8)) - 1]]
