"""Renders the world around the player as text for the prompt.

The narrator is the GM, so it sees secrets too; each fact is marked with who
knows it, and the prompt forbids revealing what the player's character could
not learn. (Player-facing projections are a later layer.)
"""

from __future__ import annotations

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
