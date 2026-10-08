"""Tests for undo: the effective log view, state rebuilding, history, replay and carried dice."""

import asyncio

import pytest

from aimaginarium.api import LocalServer, Role, SubmitAction, Undo
from aimaginarium.ui.cli import play
from aimaginarium.engine import PLAYER_ID, D20Rules, Game, create_demo_world
from aimaginarium.prompts import PromptBuilder
from aimaginarium.world import UndoError, WorldStore, verify_replay
from engine_helpers import make_game, reply, stealth_check


class Dice:
    """Rolls the given numbers in order."""

    def __init__(self, *dice):
        self.dice = list(dice)

    def randint(self, low, high):
        return self.dice.pop(0)


def new_game(replies, dice=(14,)):
    store = WorldStore.open()
    create_demo_world(store)
    game, provider = make_game(store, replies)
    game.rules = D20Rules(Dice(*dice))
    return game, provider


def run(coro):
    return asyncio.run(coro)


async def play_turn(game, text):
    """Plays a whole turn and returns the events."""
    events = [e async for e in game.take_turn(PLAYER_ID, text)]
    if game.awaiting_roll:
        events += [e async for e in game.resolve_check()]
    return events


def dice_rolled(events):
    return [e.roll.die for e in events if type(e).__name__ == "CheckCalled"]


CHANGE = [{"op": "update", "entity": PLAYER_ID, "set": {"sheet.mood": "calm"}}]
CREATE = [{"op": "create", "ref": "@coin", "kind": "item", "name": "Silver coin", "parent_id": PLAYER_ID}]


# -- the store -----------------------------------------------------------------

def test_the_effective_log_leaves_out_retracted_turns_but_the_raw_log_keeps_them():
    game, _ = new_game([reply(["One."], CHANGE), reply(["Two."], CREATE)])
    run(play_turn(game, "first"))
    run(play_turn(game, "second"))
    store = game.store
    raw_before = len(store.events(include_retracted=True))
    assert game.undo() == 2
    assert {e.turn_id for e in store.events()} <= {None, 1}
    assert len(store.events(include_retracted=True)) == raw_before + 1  # only the retraction was added
    assert [e.kind for e in store.events(kind="turn.retracted")] == ["turn.retracted"]
    assert store.events(turn=2) == [] and store.events(turn=2, include_retracted=True)


def test_state_is_rebuilt_without_the_retracted_turn_and_replay_still_matches():
    game, _ = new_game([reply(["One."], CHANGE), reply(["Two."], CREATE)])
    run(play_turn(game, "first"))
    run(play_turn(game, "second"))
    store = game.store
    assert store.find(name="Silver coin")
    game.undo()
    assert store.find(name="Silver coin") == []
    assert store.get_entity(PLAYER_ID).data["sheet"]["mood"] == "calm"  # turn 1 is still in
    assert verify_replay(store) == []  # the replay check goes through the effective view
    game.undo()
    assert "mood" not in store.get_entity(PLAYER_ID).data.get("sheet", {})
    assert verify_replay(store) == []


def test_ids_and_turn_numbers_are_not_reused_after_an_undo():
    game, _ = new_game([reply(["One."], CREATE), reply(["Two."], CREATE)])
    run(play_turn(game, "first"))
    first = game.store.find(name="Silver coin")[0].id
    game.undo()
    run(play_turn(game, "again"))
    assert game.store.find(name="Silver coin")[0].id != first and game.turn_id == 2


def test_only_the_latest_turn_can_be_taken_back():
    game, _ = new_game([reply(["One."]), reply(["Two."])])
    run(play_turn(game, "first"))
    run(play_turn(game, "second"))
    with pytest.raises(UndoError):
        game.store.retract_turn(1, actor="engine")
    assert game.store.last_turn() == 2


def test_nothing_to_undo_on_a_fresh_world():
    game, _ = new_game([])
    assert game.undo() is None


# -- the conversation ------------------------------------------------------------

def test_history_never_includes_a_retracted_turn_live_or_after_a_restart():
    game, provider = new_game([reply(["One."]), reply(["Two."]), reply(["Three."])])
    run(play_turn(game, "first"))
    run(play_turn(game, "second"))
    game.undo()
    assert [m.content for m in game.history] == ["first", "One."]
    restored = Game(game.store, game.llm, PromptBuilder.from_directory(), PLAYER_ID)
    assert restored.history == game.history  # _load_history reads the effective view
    run(play_turn(game, "third"))
    sent = [m.content for m in provider.requests[-1].messages]
    assert "second" not in " ".join(sent) and "Two." not in " ".join(sent)


def test_undoing_the_opening_lets_the_story_begin_again():
    game, _ = new_game([reply(["Opening."])])

    async def open_it():
        return [e async for e in game.open_scene()]

    run(open_it())
    assert game.begun
    game.undo()
    assert not game.begun and game.history == []


# -- checks: undo must not become a reroll -----------------------------------------

def test_a_paused_check_can_be_taken_back_and_its_die_is_reused():
    check = stealth_check()
    game, _ = new_game([reply(["You creep."], check=check), reply(["You slip."]), reply(["You creep."], check=check),
                        reply(["You slip."])], dice=(14, 3))
    run(play_turn(game, "I sneak."))  # rolls 14 and resolves
    assert game.undo() == 1 and not game.awaiting_roll
    events = run(play_turn(game, "I sneak, more carefully."))
    assert dice_rolled(events) == [14]  # the carried die, not the 3 the dice would give next


def test_a_pending_check_taken_back_before_the_roll_also_carries_its_die():
    game, _ = new_game([reply(["You creep."], check=stealth_check()), reply(["You creep."], check=stealth_check()),
                        reply(["Done."])], dice=(14, 3))

    async def start():
        return [e async for e in game.take_turn(PLAYER_ID, "I sneak.")]

    run(start())
    assert game.awaiting_roll and game.undo() == 1 and not game.awaiting_roll
    assert dice_rolled(run(play_turn(game, "I sneak."))) == [14]


def test_carried_dice_come_back_in_the_order_the_turns_are_replayed():
    check = stealth_check()
    game, _ = new_game([reply(["a"], check=check), reply(["b"])] * 5, dice=(14, 9, 5))
    run(play_turn(game, "one"))
    run(play_turn(game, "two"))
    game.undo()
    game.undo()
    rolled = dice_rolled(run(play_turn(game, "one again"))) + dice_rolled(run(play_turn(game, "two again")))
    assert rolled == [14, 9]
    assert dice_rolled(run(play_turn(game, "three"))) == [5]  # carried dice are used up


def test_a_die_is_carried_until_a_kept_check_uses_it_and_then_not_again():
    check = stealth_check()
    game, _ = new_game([reply(["a"], check=check), reply(["b"])] * 4, dice=(14, 3))
    rolled = dice_rolled(run(play_turn(game, "one")))
    for text in ("again", "and again"):
        game.undo()  # each retry reuses the same die, even a retry of a retry
        rolled += dice_rolled(run(play_turn(game, text)))
    rolled += dice_rolled(run(play_turn(game, "fresh")))  # the carried die was used by a kept turn
    assert rolled == [14, 14, 14, 3]


# -- clients -----------------------------------------------------------------------

def test_terminal_undo_is_for_the_dev_role_only():
    def session_output(role):
        game, _ = new_game([reply(["One."])])
        out, lines = [], iter(["first", "/undo", "/undo", "/quit"])

        async def ask(prompt):
            return next(lines)

        session = LocalServer(game, dev_enabled=True).connect(role)
        run(play(session, ask, lambda text="", end="\n": out.append(text + end), opening=False))
        return "".join(out)

    dev = session_output(Role.DEV)
    assert "Took back turn 1." in dev and "There is no turn to take back." in dev
    assert "Unknown command /undo" in session_output(Role.PLAYER)
