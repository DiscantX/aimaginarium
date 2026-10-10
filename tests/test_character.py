"""Tests for the character model and the engine's player view of a sheet."""

from aimaginarium.engine import create_demo_world, render_player_view
from aimaginarium.ui.character import (
    CharacterView, character_from_dict, character_from_member, characters_from_view, demo_character, modifier, signed,
)
from aimaginarium.ui.party import Controller, PartyMember, party_from_view
from aimaginarium.world import Update, WorldStore


def test_modifiers_follow_the_5e_formula_and_are_signed():
    assert [modifier(s) for s in (1, 8, 9, 10, 11, 15, 20)] == [-5, -1, -1, 0, 0, 2, 5]
    assert (signed(2), signed(0), signed(-1)) == ("+2", "+0", "-1")


def test_a_character_reads_whatever_the_projection_has_and_leaves_the_rest_empty():
    view = character_from_dict({"name": "Kael", "class": "Fighter", "level": 3, "race": "Human", "hp": 20, "max_hp": 24,
                                "abilities": {"str": 16}, "skills": {"athletics": 3}},
                               carrying=[{"name": "Shortsword"}, "Rope"], mine=True)
    assert (view.name, view.identity, view.hp_fraction, view.mine) == ("Kael", "Human · Fighter 3", 20 / 24, True)
    assert [i.name for i in view.inventory] == ["Shortsword", "Rope"]
    bare = character_from_dict({"name": "Stranger"})
    assert (bare.identity, bare.hp_fraction, bare.abilities, bare.spells, bare.inventory) == ("", None, {}, (), ())


def test_identity_without_a_class_uses_the_level_and_skips_what_is_unknown():
    assert CharacterView("A", level=2, alignment="True Neutral").identity == "Level 2 · True Neutral"
    assert CharacterView("A").identity == ""


def test_a_view_without_a_party_is_the_players_own_character_and_a_party_entry_may_carry_its_own():
    view = {"character": {"name": "Kael", "class": "Fighter"}, "carrying": [{"name": "Shortsword"}]}
    members = party_from_view(view)
    (own,) = characters_from_view(view, members).values()
    assert own.mine and own.name == "Kael" and own.inventory[0].name == "Shortsword"
    view = {"party": [{"id": "a", "name": "Kael", "mine": True, "character": {"name": "Kael", "spells": ["Shield"]}},
                      {"id": "b", "name": "Mira", "class_name": "Wizard", "level": 3}]}
    characters = characters_from_view(view, party_from_view(view))
    assert characters["a"].spells == ("Shield",) and characters["a"].mine
    assert characters["b"].class_name == "Wizard" and not characters["b"].mine and characters["b"].spells == ()


def test_a_member_with_nothing_but_a_card_still_makes_a_character():
    member = PartyMember("b", "Mira", class_name="Wizard", level=3, hp=5, max_hp=20, statuses=("prone",),
                         controller=Controller.LLM_MCP)
    view = character_from_member(member)
    assert (view.name, view.identity, view.hp, view.statuses, view.controller) == ("Mira", "Wizard 3", 5, ("prone",), Controller.LLM_MCP)


def test_a_demo_character_is_stable_and_keeps_the_card_fields():
    member = PartyMember("demo-1", "Torvik", class_name="Cleric", level=3, hp=9, max_hp=27, statuses=("poisoned",))
    first, second = demo_character(member), demo_character(member)
    assert first == second and first.hp == 9 and first.statuses == ("poisoned",) and first.spells
    assert demo_character(PartyMember("demo-2", "Gorm", class_name="Ranger", level=3)).spells  # casters only
    assert demo_character(PartyMember("demo-3", "Brannoch", class_name="Barbarian", level=3)).spells == ()


def test_the_player_view_carries_the_players_own_sheet_but_only_whitelisted_keys():
    store = WorldStore.open()
    player_id = create_demo_world(store)
    store.commit([Update(entity=player_id, set={"sheet.gm_notes": "secretly the lost heir", "sheet.inspiration": True})],
                 actor="system")
    character = render_player_view(store, player_id)["character"]
    assert character["class"] == "Fighter" and character["abilities"]["str"] == 16 and character["inspiration"] is True
    assert character["skills"]["athletics"] == 3
    assert "gm_notes" not in character and "sheet" not in character
