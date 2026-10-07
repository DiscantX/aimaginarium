"""Tests for the terminal client, with scripted input and output."""

import asyncio
import re

from aimaginarium.cli import main, play
from engine_helpers import make_game, reply
from aimaginarium.engine import PLAYER_ID, create_demo_world, Game
from aimaginarium.prompts import PromptBuilder
from aimaginarium.world import WorldStore


def run_session(game, inputs, opening=False):
    asked, output = [], []
    lines = iter(inputs)

    async def ask(prompt):
        plain = re.sub(r'\033\[[0-9;]*m', '', prompt)
        asked.append(plain)
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    def out(text="", end="\n"):
        output.append(text + end)

    asyncio.run(play(game, ask, out, opening=opening))
    return asked, "".join(output)


def fresh_game(replies, die=15):
    store = WorldStore.open()
    create_demo_world(store)
    return make_game(store, replies, die)[0]


def test_plain_turn_prints_the_narration_and_quits():
    asked, text = run_session(fresh_game([reply(["Marta nods."])]), ["I greet Marta.", "/quit"])
    assert "Marta nods." in text and asked == ["> ", "> "]


def test_check_pauses_for_the_roll_and_never_shows_the_difficulty():
    check = {"skill": "stealth", "difficulty": 12, "reason": "x"}
    game = fresh_game([reply(["You creep."], check=check), reply(["You slip past."])], die=14)
    asked, text = run_session(game, ["I sneak.", "", "/quit"])
    assert asked[1].startswith("\n[Stealth check] Press Enter") and "You rolled 14 +1 = 15." in text
    assert text.index("You creep.") < text.index("You rolled") < text.index("You slip past.")
    assert "12" not in text


def test_rejected_changes_are_explained_without_stopping():
    changes = [{"op": "move", "entity": "item-99", "to": PLAYER_ID}]
    _, text = run_session(fresh_game([reply(["Done."], changes)]), ["I take it.", "/quit"])
    assert "were not accepted" in text and "world is unchanged" in text


def test_opening_and_state_command():
    game = fresh_game([reply(["A", "B", "C", "D", "E", "F", "G"])])
    _, text = run_session(game, ["/state", "/quit"], opening=True)
    assert "A" in text and "B" in text and text.index("A") < text.index("Location:") and "Marta [char-2]" in text


def test_blank_lines_are_ignored_and_end_of_input_quits():
    asked, _ = run_session(fresh_game([]), ["", "   "])
    assert asked == ["> ", "> ", "> "]


def test_main_reports_a_missing_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AIMAGINARIUM_CONFIG", raising=False)
    assert main(["--world", str(tmp_path / "w.sqlite")]) == 2
    assert "configuration problem" in capsys.readouterr().err


def test_conversation_history_persists_across_restart():
    store = WorldStore.open()
    create_demo_world(store)
    game1, factory = make_game(store, [reply(["Hello world."]), reply(["Second response."])])
    run_session(game1, ["First action.", "/quit"], opening=True)

    game2 = Game(store, factory, PromptBuilder.from_directory(), PLAYER_ID)
    assert len(game2._history) == 4
    assert game2._history[0].content == "(The story begins.)"
    assert game2._history[1].content == "Hello world."
    assert game2._history[2].content == "First action."
    assert game2._history[3].content == "Second response."
