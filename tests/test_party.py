"""Tests for the party model shared by the clients."""

from aimaginarium.ui.party import Controller, PartyMember, demo_party, party_from_view


def test_a_view_without_a_party_is_the_player_alone():
    party = party_from_view({"character": {"name": "Kael", "class": "Fighter", "level": 3, "hp": 20, "max_hp": 24}})
    assert [(m.name, m.class_name, m.level, m.mine) for m in party] == [("Kael", "Fighter", 3, True)]


def test_a_character_without_sheet_numbers_still_makes_a_member():
    (kael,) = party_from_view({"character": {"name": "Kael"}})
    assert kael.hp_fraction is None and kael.subtitle == "" and kael.statuses == ()


def test_a_view_with_a_party_uses_it_and_its_controllers():
    view = {"party": [{"id": "a", "name": "Kael", "mine": True},
                      {"id": "b", "name": "Mira", "controller": "llm-mcp", "statuses": ["prone"]}]}
    kael, mira = party_from_view(view)
    assert (kael.mine, kael.controller) == (True, Controller.HUMAN)
    assert (mira.mine, mira.controller, mira.statuses) == (False, Controller.LLM_MCP, ("prone",))


def test_hit_point_fraction_is_clamped_and_unknown_without_a_maximum():
    assert PartyMember("a", "A", hp=30, max_hp=20).hp_fraction == 1.0
    assert PartyMember("a", "A", hp=-3, max_hp=20).hp_fraction == 0.0
    assert PartyMember("a", "A", hp=5).hp_fraction is None


def test_subtitle_combines_class_and_level():
    assert PartyMember("a", "A", class_name="Rogue", level=2).subtitle == "Rogue 2"
    assert PartyMember("a", "A", class_name="Rogue").subtitle == "Rogue"
    assert PartyMember("a", "A", level=2).subtitle == "Level 2"


def test_a_demo_party_keeps_the_player_first_and_can_be_any_size():
    player = PartyMember("self", "Kael", mine=True)
    assert [m.name for m in demo_party(player, 1)] == ["Kael"]
    assert len(demo_party(player, 0)) == 1
    big = demo_party(player, 20)
    assert len(big) == 20 and len({m.id for m in big}) == 20 and len({m.name for m in big}) == 20  # repeats are numbered
    first = demo_party(player, 3)[0]
    assert first.mine and first.hp == 24  # blanks are filled with stand-ins so the card can be judged
