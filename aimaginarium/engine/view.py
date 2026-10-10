"""Renders the world around the player as text for the prompt.

The narrator is the GM, so it sees secrets too; each fact is marked with who
knows it, and the prompt forbids revealing what the player's character could
not learn. (Player-facing projections are a later layer.)
"""

from __future__ import annotations

import copy
from typing import Any

from ..world import Entity, Fact, WorldStore


def _fact(fact: Fact) -> str:
    """Formats a fact with who knows it."""
    if fact.known_by is None:
        return f"{fact.text} (public)"
    who = ", ".join(fact.known_by) or "the GM only"
    return f"{fact.text} (secret; known to {who})"


def _entity(entity: Entity) -> str:
    """Formats an entity as one line."""
    line = f"{entity.name} [{entity.id}], {entity.kind}"
    if description := entity.data.get("description"):
        line += f": {description.rstrip('.')}"
    if entity.established:
        line += ". Facts: " + "; ".join(_fact(f) for f in entity.established)
    return line


def render_state(store: WorldStore, player_id: str) -> dict[str, str]:
    """Describes the player's surroundings and the player's character.

    Args:
        store: The world.
        player_id: The player character's entity id.

    Returns:
        ``world_state`` and ``character`` text, for the prompt's state fragments.
    """
    player = store.get_entity(player_id)
    location_id = store.location_of(player_id)
    lines = []
    if location_id:
        here = store.get_entity(location_id)
        lines.append(f"Location: {_entity(here)}")
        exits = [f"{store.get_entity(c['to_id']).name} [{c['to_id']}] via {c['label']}" for c in store.connections(location_id)]
        lines.append("Exits: " + ("; ".join(exits) or "none"))
        others = [e for e in store.children(location_id) if e.id != player_id]
        lines.append("Here:" + ("".join(f"\n- {_entity(e)}" for e in others) or " nothing else"))
    skills = player.data.get("sheet", {}).get("skills", {})
    character = [_entity(player)]
    if skills:
        character.append("Skills: " + ", ".join(f"{name} {bonus:+d}" for name, bonus in skills.items()))
    carried = store.children(player_id)
    character.append("Carrying: " + (", ".join(f"{e.name} [{e.id}]" for e in carried) or "nothing"))
    known = store.known_facts(player_id)
    if known:
        character.append("Secrets the character knows: " + "; ".join(f.text for f in known))
    return {"world_state": "\n".join(lines), "character": "\n".join(character)}


SHEET_KEYS = ("race", "class", "level", "background", "alignment", "ac", "proficiency", "inspiration", "hp", "max_hp",
              "temp_hp", "xp", "xp_next", "abilities", "proficiencies", "equipment", "coins", "features", "spells",
              "statuses")
"""The parts of a character sheet the player's own view carries (a whitelist: nothing else in a sheet is shown)."""


def _known(entity: Entity, player_id: str) -> list[str]:
    """Returns the facts about an entity that the player's character may know."""
    return [f.text for f in entity.established if f.known_by is None or player_id in f.known_by]


def _seen(entity: Entity, player_id: str) -> dict[str, Any]:
    """Describes an entity by what the player can perceive: no ids, no hidden facts."""
    return {"name": entity.name, "kind": entity.kind, "description": entity.data.get("description", ""),
            "facts": _known(entity, player_id)}


def render_player_view(store: WorldStore, player_id: str) -> dict[str, Any]:
    """Describes the world as the player's character can know it (a projection).

    Unlike :func:`render_state`, this never includes entity ids, secrets the
    character does not know, or anything the GM alone knows.

    Args:
        store: The world.
        player_id: The player character's entity id.

    Returns:
        ``location``, ``exits``, ``here``, ``character`` (with the sheet keys in :data:`SHEET_KEYS` when it has
        them) and ``carrying``.
    """
    player = store.get_entity(player_id)
    location_id = store.location_of(player_id)
    view: dict[str, Any] = {"location": None, "exits": [], "here": []}
    if location_id:
        view["location"] = _seen(store.get_entity(location_id), player_id)
        view["exits"] = [{"to": store.get_entity(c["to_id"]).name, "label": c["label"]} for c in store.connections(location_id)]
        view["here"] = [_seen(e, player_id) for e in store.children(location_id) if e.id != player_id]
    sheet = player.data.get("sheet", {})
    view["character"] = {**_seen(player, player_id), "skills": dict(sheet.get("skills", {})),
                         **{key: copy.deepcopy(sheet[key]) for key in SHEET_KEYS if key in sheet}}
    view["carrying"] = [_seen(e, player_id) for e in store.children(player_id)]
    return view
