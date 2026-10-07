"""Tests for the terminal client, with scripted input and output."""

import asyncio

from aimaginarium.api import LocalServer, Role
from aimaginarium.cli import main, play
from engine_helpers import make_game, reply, stealth_check
from aimaginarium.engine import PLAYER_ID, create_demo_world, Game
from aimaginarium.prompts import PromptBuilder
from aimaginarium.world import WorldStore


def run_session(game, inputs, opening=False, role=Role.PLAYER):
    asked, output = [], []
    lines = iter(inputs)

    async def ask(prompt):
        asked.append(prompt)
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    def out(text="", end="\n"):
        output.append(text + end)

    session = LocalServer(game, dev_enabled=True).connect(role)
    asyncio.run(play(session, ask, out, opening=opening))
    return asked, "".join(output)


def fresh_game(replies, die=15):
    store = WorldStore.open()
    create_demo_world(store)
    return make_game(store, replies, die)[0]


def test_plain_turn_prints_the_narration_and_quits():
    asked, text = run_session(fresh_game([reply(["Marta nods."])]), ["I greet Marta.", "/quit"])
    assert "Marta nods." in text and asked == ["> ", "> "]


def test_check_shows_the_difficulty_and_pauses_for_the_roll():
    check = stealth_check("x")
    game = fresh_game([reply(["You creep."], check=check), reply(["You slip past."])], die=14)
    asked, text = run_session(game, ["I sneak.", "", "/quit"])
    assert asked[1].startswith("\n[Stealth check, difficulty 12] Press Enter") and "You rolled 14 +1 = 15." in text
    assert text.index("You creep.") < text.index("You rolled") < text.index("You slip past.")


def test_rejected_changes_are_explained_without_stopping():
    changes = [{"op": "move", "entity": "item-99", "to": PLAYER_ID}]
    _, text = run_session(fresh_game([reply(["Done."], changes), '{"changes": []}']), ["I take it.", "/quit"])
    assert "were not accepted" in text and "world is unchanged" in text


def test_opening_and_state_command_show_the_players_view_not_the_gms():
    game = fresh_game([reply(["A", "B", "C", "D", "E", "F", "G"])])
    _, text = run_session(game, ["/state", "/state gm", "/quit"], opening=True)
    assert text.index("A\n\nB") < text.index("Location:") and "Marta:" in text
    assert "[char-2]" not in text and "secret" not in text


def test_dev_role_can_read_the_gm_view():
    game = fresh_game([reply(["A"])])
    _, text = run_session(game, ["/state gm", "/quit"], opening=True, role=Role.DEV)
    assert "Marta [char-2]" in text and "secret; known to char-2" in text


def test_resuming_replays_the_story():
    store = WorldStore.open()
    create_demo_world(store)
    game1, factory = make_game(store, [reply(["Hello world."]), reply(["Second response."])])
    run_session(game1, ["First action.", "/quit"], opening=True)
    game2 = Game(store, factory, PromptBuilder.from_directory(), PLAYER_ID)
    _, text = run_session(game2, ["/quit"])
    assert "> First action." in text and "Hello world." in text


def test_unknown_slash_commands_are_never_sent_to_the_narrator():
    _, text = run_session(fresh_game([]), ["/state gm", "/frobnicate", "/quit"])
    assert "Unknown command /state" in text and "Unknown command /frobnicate" in text


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
    assert len(game2.history) == 4
    assert game2.history[0].content == "(The story begins.)"
    assert game2.history[1].content == "Hello world."
    assert game2.history[2].content == "First action."
    assert game2.history[3].content == "Second response."


def test_pending_input_is_discarded_on_windows(monkeypatch):
    import sys
    import types
    from aimaginarium.cli import discard_pending_input

    keys = list("\r\r\r")
    fake = types.SimpleNamespace(kbhit=lambda: bool(keys), getwch=lambda: keys.pop())
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    discard_pending_input()
    assert keys == []


def test_pending_input_is_flushed_on_unix_and_ignored_when_not_a_terminal(monkeypatch):
    import sys
    import types
    from aimaginarium.cli import discard_pending_input

    calls = []
    fake = types.SimpleNamespace(tcflush=lambda fd, how: calls.append((fd, how)), TCIFLUSH=0)
    monkeypatch.setitem(sys.modules, "termios", fake)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 7, raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    discard_pending_input()
    assert calls == []
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    discard_pending_input()
    assert calls == [(7, 0)]
