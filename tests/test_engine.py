"""Tests for the game facade: turns, checks, commits, failures and the rules."""

import asyncio
import json

import pytest

from engine_helpers import FixedDice, make_game, reply, stealth_check
from aimaginarium.engine import (
    ChangesRejected, CheckCalled, Committed, D20Rules, Game, Narration, PLAYER_ID, ReplyUnreadable, create_demo_world,
    render_state,
)
from aimaginarium.llm import Capabilities, ProviderFactory, ProviderUnavailableError
from aimaginarium.llm.providers.fake import FakeProvider
from aimaginarium.prompts import PromptBuilder
from aimaginarium.world import WorldStore


@pytest.fixture
def store():
    with WorldStore.open() as s:
        create_demo_world(s)
        yield s


def play(gen):
    async def collect():
        return [event async for event in gen]
    return asyncio.run(collect())


def kinds(store, turn=None):
    return [e.kind for e in store.events(turn=turn)] if turn else [e.kind for e in store.events()]


def test_plain_turn_streams_narration_and_commits_changes(store):
    game, provider = make_game(store, [reply(["Marta nods.", "She hands you the key."], [{"op": "move", "entity": "item-3", "to": PLAYER_ID}])])
    events = play(game.take_turn(PLAYER_ID, "I ask Marta for the key."))
    assert "".join(e.text for e in events if isinstance(e, Narration)) == "Marta nods.\n\nShe hands you the key."
    assert isinstance(events[-1], Committed)
    assert store.get_entity("item-3").parent_id == PLAYER_ID
    assert kinds(store, turn=1) == ["player.action", "llm.call", "entity.moved"]


def test_request_has_stable_system_and_state_last(store):
    game, provider = make_game(store, [reply(["One."]), reply(["Two."])])
    play(game.take_turn(PLAYER_ID, "I look around."))
    play(game.take_turn(PLAYER_ID, "I wait."))
    first, second = provider.requests
    assert first.system == second.system
    assert "wiping the same mug" not in first.system and "wiping the same mug" in first.messages[-1].content
    assert first.messages[-1].content.endswith("I look around.")
    assert [m.role for m in second.messages] == ["user", "assistant", "user"]
    assert second.messages[0].content == "I look around." and second.messages[1].content == "One."  # history holds no state
    assert second.schema is not None and list(second.schema.model_fields)[:2] == ["narration", "check"]


def test_check_turn_commits_the_request_before_the_roll_and_uses_two_calls(store):
    check = stealth_check("The guard may notice.")
    game, provider = make_game(
        store,
        [reply(["You creep forward."], check=check),
         reply(["You slip past."], [{"op": "update", "entity": PLAYER_ID, "set": {"sheet.sneaked": True}}])],
        die=14)

    async def run():
        gen = game.take_turn(PLAYER_ID, "I sneak past the guard.")
        seen = []
        async for event in gen:
            seen.append(event)
            if isinstance(event, CheckCalled):
                # The player has not pressed the button yet: the request is logged, the roll is not.
                assert "check.requested" in kinds(store) and "roll" not in kinds(store)
        return seen

    events = asyncio.run(run())
    called = next(e for e in events if isinstance(e, CheckCalled))
    assert (called.roll.die, called.roll.modifier, called.roll.total, called.roll.classification) == (14, 1, 15, "success")
    assert (called.ruling.tier, called.ruling.base, called.ruling.difficulty) == ("easy", 10, 12)
    requested = store.events(kind="check.requested")[0].payload
    assert requested["tier"] == "easy" and requested["difficulty"] == 12 and requested["base"] == 10
    assert requested["adjustments"] == [{"what": "creaking floor", "delta": 1}, {"what": "dim light", "delta": 1}]
    assert requested["factors"][0] == {"what": "creaking floor", "effect": "harder", "size": "small"}
    assert "".join(e.text for e in events if isinstance(e, Narration)) == "You creep forward.You slip past."
    assert kinds(store, turn=1) == ["player.action", "llm.call", "check.requested", "roll", "llm.call", "entity.updated"]
    assert store.get_entity(PLAYER_ID).data["sheet"]["sneaked"] is True
    assert len(provider.requests) == 2
    second = provider.requests[1]
    assert second.messages[-2].role == "assistant" and second.messages[-2].content == "You creep forward."
    assert "success" in second.messages[-1].content and "stealth" in second.messages[-1].content
    update = store.events(kind="entity.updated")[-1]
    assert [e.kind for e in store.causal_chain(update.seq)] == ["player.action", "check.requested", "roll"]


def test_critical_failure_selects_its_own_instruction(store):
    check = {"skill": "athletics", "tier": "easy", "reason": "The wall is slick."}
    game, provider = make_game(store, [reply(["You jump."], check=check), reply(["You fall."])], die=1)
    play(game.take_turn(PLAYER_ID, "I leap the wall."))
    assert "critical failure" in provider.requests[1].messages[-1].content


BAD = [{"op": "move", "entity": "item-99", "to": PLAYER_ID}]
GOOD = [{"op": "move", "entity": "item-3", "to": PLAYER_ID}]


def repair(changes):
    return json.dumps({"changes": changes})


def test_rejected_changes_are_repaired_once_and_committed(store):
    game, provider = make_game(store, [reply(["You take the key."], BAD), repair(GOOD)])
    events = play(game.take_turn(PLAYER_ID, "I grab the key."))
    assert [type(e).__name__ for e in events if not isinstance(e, Narration)] == ["Repairing", "Committed"]
    assert store.get_entity("item-3").parent_id == PLAYER_ID
    assert kinds(store, turn=1) == ["player.action", "llm.call", "changes.rejected", "llm.call", "entity.moved"]
    request = provider.requests[1]
    assert "item-99" in request.messages[-1].content and "You take the key." in request.messages[-1].content
    assert "does not exist" in request.messages[-1].content and "Rusty key [item-3]" in request.messages[-1].content


def test_a_repair_that_is_still_rejected_leaves_the_world_untouched(store):
    game, _ = make_game(store, [reply(["You take it."], BAD), repair(BAD)])
    events = play(game.take_turn(PLAYER_ID, "I grab a sword."))
    assert isinstance(events[-1], ChangesRejected) and events[-1].errors[0].index == 0
    assert kinds(store).count("changes.rejected") == 2
    assert store.get_entity("item-3").parent_id == "loc-1"


def test_an_empty_or_failed_repair_reports_the_original_rejection(store):
    game, _ = make_game(store, [reply(["One."], BAD), repair([])])
    assert isinstance(play(game.take_turn(PLAYER_ID, "I try."))[-1], ChangesRejected)
    game, _ = make_game(store, [reply(["Two."], BAD), ProviderUnavailableError("busy", attempts=1, waited=0)])
    events = play(game.take_turn(PLAYER_ID, "I try again."))
    assert isinstance(events[-1], ChangesRejected) and "llm.failed" in kinds(store)


def test_repair_after_a_check_commits_with_the_roll_as_cause(store):
    check = {"skill": "stealth", "tier": "medium", "reason": "x"}
    game, _ = make_game(store, [reply(["You creep."], check=check), reply(["You take it."], BAD), repair(GOOD)])
    play(game.take_turn(PLAYER_ID, "I sneak to the key."))
    moved = store.events(kind="entity.moved")[-1]
    assert [e.kind for e in store.causal_chain(moved.seq)] == ["player.action", "check.requested", "roll"]


def test_unreadable_reply_is_reported_and_not_remembered(store):
    game, provider = make_game(store, ["this is not json", reply(["Fine."])])
    events = play(game.take_turn(PLAYER_ID, "I shout."))
    assert isinstance(events[-1], ReplyUnreadable) and "reply.invalid" in kinds(store)
    play(game.take_turn(PLAYER_ID, "I try again."))
    assert [m.content for m in provider.requests[1].messages if m.role == "user"][0].endswith("I try again.")
    assert len(provider.requests[1].messages) == 1


def test_unavailable_provider_is_reported(store):
    game, _ = make_game(store, [ProviderUnavailableError("busy", attempts=6, waited=45)])
    events = play(game.take_turn(PLAYER_ID, "I wave."))
    assert isinstance(events[-1], ReplyUnreadable) and "could not be reached" in events[-1].reason
    assert "llm.failed" in kinds(store)


def test_only_the_player_can_act(store):
    game, _ = make_game(store, [])
    with pytest.raises(ValueError):
        play(game.take_turn("char-2", "I steal."))


def test_opening_scene_narrates_and_is_remembered(store):
    game, provider = make_game(store, [reply(["World.", "Town.", "Here."]), reply(["Later."])])
    events = play(game.open_scene())
    assert "".join(e.text for e in events if isinstance(e, Narration)) == "World.\n\nTown.\n\nHere."
    play(game.take_turn(PLAYER_ID, "I look."))
    assert provider.requests[1].messages[1].content == "World.\n\nTown.\n\nHere."
    assert provider.requests[0].schema.model_json_schema()["properties"]["narration"]["minItems"] == 7


def test_history_is_limited_and_starts_on_a_player_message(store):
    game, provider = make_game(store, [reply([str(i)]) for i in range(4)])
    game.history_limit = 3
    for i in range(4):
        play(game.take_turn(PLAYER_ID, f"act {i}"))
    messages = provider.requests[3].messages
    assert messages[0].role == "user" and len(messages) <= 4


@pytest.mark.parametrize("die,difficulty,expected", [
    (1, 5, "critical_failure"), (20, 30, "critical_success"), (5, 20, "failure"),
    (10, 12, "narrow_success"), (12, 12, "narrow_success"), (13, 12, "success"), (9, 12, "failure"),
])
def test_rules_classify_rolls(store, die, difficulty, expected):
    roll = D20Rules(FixedDice(die)).roll(store.get_entity(PLAYER_ID), "perception", difficulty)  # perception +2
    assert roll.classification == expected and roll.total == die + 2 and roll.margin == roll.total - difficulty


def test_unknown_skill_has_no_bonus(store):
    assert D20Rules(FixedDice(10)).roll(store.get_entity(PLAYER_ID), "Juggling", 5).modifier == 0


def test_scene_view_shows_ids_exits_inventory_and_secrets(store):
    state = render_state(store, PLAYER_ID)
    assert "Marta [char-2]" in state["world_state"] and "secret; known to char-2" in state["world_state"]
    assert "Market Square [loc-2] via front door" in state["world_state"]
    assert "Shortsword [item-1]" in state["character"] and "athletics +3" in state["character"]
    assert ".." not in state["world_state"]


def test_restored_history_matches_the_live_history_including_check_turns(store):
    check = {"skill": "stealth", "tier": "medium", "reason": "x"}
    live, _ = make_game(store, [reply(["You creep."], check=check), reply(["You slip past."]), reply(["Marta nods."])])
    play(live.take_turn(PLAYER_ID, "I sneak."))
    play(live.take_turn(PLAYER_ID, "I greet Marta."))
    restored, _ = make_game(store, [])
    assert restored._history == live._history
    assert restored._history[1].content == "You creep.\n\nYou slip past."


def test_check_without_a_number_reaches_the_outcome_prompt_with_the_tier(store):
    game, provider = make_game(store, [reply(["You creep."], check=stealth_check()), reply(["You slip past."])])
    play(game.take_turn(PLAYER_ID, "I sneak."))
    state = provider.requests[1].messages[-1].content
    assert "difficulty 12" in state and "judged easy" in state
    assert "Never give a number" in provider.requests[0].system


def rule(tier, *factors):
    from aimaginarium.engine import CheckRequest
    return D20Rules().rule(CheckRequest(skill="x", tier=tier, factors=[
        {"what": w, "effect": e, "size": z} for w, e, z in factors]))


def test_tier_gives_the_base_and_factors_move_it():
    assert rule("medium").difficulty == 15
    assert rule("hard", ("rain", "harder", "medium"), ("ally", "easier", "small")).difficulty == 21
    assert rule("hard", ("rain", "harder", "medium"), ("ally", "easier", "small")).adjustments == (("rain", 2), ("ally", -1))
    assert [rule(t).difficulty for t in ("very_easy", "easy", "medium", "hard", "very_hard", "nearly_impossible")] == [5, 10, 15, 20, 25, 30]


def test_adjustment_is_limited_and_difficulty_stays_in_range():
    ruling = rule("hard", *[(f"c{i}", "harder", "large") for i in range(4)])
    assert (ruling.adjustment, ruling.difficulty) == (6, 26) and sum(d for _, d in ruling.adjustments) == 16
    assert rule("very_easy", ("a", "easier", "large"), ("b", "easier", "large")).difficulty == 1
    assert rule("nearly_impossible", ("a", "harder", "large"), ("b", "harder", "large")).difficulty == 36


def test_unknown_words_from_weaker_models_are_normalised():
    from aimaginarium.engine import CheckRequest
    check = CheckRequest.model_validate({"skill": "x", "tier": "Very Hard", "factors": [
        {"what": "a", "effect": "HARDER", "size": "huge"}, {"what": "b", "effect": "helps", "size": "Large"}]})
    assert check.tier == "very_hard" and check.factors[0].size == "small" and check.factors[1].effect == "harder"
    assert CheckRequest.model_validate({"skill": "x", "tier": "moderate"}).tier == "medium"


def test_tier_table_matches_the_schema_and_the_schema_lists_the_choices():
    from typing import get_args
    from aimaginarium.engine import CheckRequest
    from aimaginarium.engine.replies import Size, Tier
    from aimaginarium.engine.rules import SIZES, TIERS
    assert set(TIERS) == set(get_args(Tier)) and set(SIZES) == set(get_args(Size))
    schema = CheckRequest.model_json_schema()
    assert set(schema["properties"]["tier"]["enum"]) == set(TIERS) and "difficulty" not in schema["properties"]
