"""Terminal client.

It talks to the game only through an API session (:mod:`aimaginarium.api`), in
the same process, so it sees what any other client would see.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Awaitable, Callable, Optional, Sequence

from dotenv import load_dotenv

from .api import (
    ChangesRejected, CheckCalled, CommandRejected, Done, GetPlayerView, GetState, LocalServer, Narration, OpenScene,
    Quit, Repairing, ReplyUnreadable, Role, Roll, RollResult, Session, StateView, SubmitAction,
)
from .engine import Game, create_demo_world
from .llm import ConfigError, FallbackNotice, RetryNotice, factory_from_file
from .prompts import PromptBuilder
from .ui.utils import Spinner, colorize, format_assistant_message, format_player_message
from .world import WorldStore

Ask = Callable[[str], Awaitable[str]]
Show = Callable[..., None]


def discard_pending_input() -> None:
    """Drops keystrokes typed while the game was busy.

    Without this, an Enter pressed while the storyteller is still writing is
    buffered and answers the next prompt at once (a roll that happens on its own,
    a run of empty ``>`` prompts). The cost is that text typed ahead of a prompt
    is lost; nothing the player types before they can see the prompt is wanted.
    Does nothing when input is not a terminal.
    """
    if not sys.stdin.isatty():
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (ImportError, OSError, ValueError):
        pass


async def ask_input(prompt: str) -> str:
    """Reads a line without blocking the event loop, ignoring anything typed earlier."""
    discard_pending_input()
    return await asyncio.to_thread(input, prompt)


def show(text: str = "", end: str = "\n") -> None:
    """Prints and flushes, wrapping text cleanly to terminal width."""
    if text and end == "\n":
        term_width = shutil.get_terminal_size().columns
        text = textwrap.fill(text, width=term_width, break_long_words=False)
    print(text, end=end, flush=True)


async def collect(stream) -> list:
    """Reads a reply stream to its end and returns the events (not the envelopes)."""
    return [envelope.event async for envelope in stream]


async def render_reply(stream, out: Show) -> tuple[Optional[CheckCalled], Done]:
    """Shows one reply stream.

    Args:
        stream: The envelopes of one command's reply.
        out: Writes text.

    Returns:
        The check that was called, if any, and the closing :class:`Done`.
    """
    spinner = Spinner()
    spinner.start()
    first, check, done = True, None, Done()
    chunks: list[str] = []

    def flush() -> None:
        """Prints the narration received so far as one formatted message."""
        if chunks:
            out(format_assistant_message("".join(chunks)), end="")
            chunks.clear()

    try:
        async for envelope in stream:
            event = envelope.event
            if first:
                spinner.stop()
                first = False
            if isinstance(event, Narration):
                chunks.append(event.text)
            elif isinstance(event, CheckCalled):
                flush()
                out()
                check = event
            elif isinstance(event, RollResult):
                out(colorize(f"You rolled {event.die} {event.modifier:+d} = {event.total}.\n", "muted"))
            elif isinstance(event, Repairing):
                flush()
                spinner.start()
                first = True
            elif isinstance(event, ChangesRejected):
                flush()
                why = f": {event.errors[0]}" if event.errors else ""
                out(colorize(f"\n\n[Some changes were not accepted{why}. The world is unchanged.]", "muted"), end="")
            elif isinstance(event, ReplyUnreadable):
                flush()
                out(colorize(f"\n\n[{event.reason}]", "muted"), end="")
            elif isinstance(event, CommandRejected):
                flush()
                out(colorize(f"\n[{event.message}]", "muted"), end="")
            elif isinstance(event, Done):
                done = event
    finally:
        spinner.stop()
        flush()
    return check, done


async def run_turn(session: Session, command, ask: Ask, out: Show) -> None:
    """Sends a turn command and, whenever a check is called, asks for the roll and sends it.

    Args:
        session: The API session.
        command: ``OpenScene`` or ``SubmitAction``.
        ask: Reads a line from the player.
        out: Writes text.
    """
    while command is not None:
        check, done = await render_reply(session.send(command), out)
        command = None
        if done.awaiting_roll and check is not None:
            await ask(colorize(f"\n[{check.skill.title()} check, difficulty {check.difficulty}] Press Enter to roll... ", "muted"))
            command = Roll()
    out("\n")


def format_player_view(view: dict) -> str:
    """Formats the player's view of the world as text."""

    def line(thing: dict) -> str:
        text = thing["name"] + (f": {thing['description']}" if thing["description"] else "")
        return text + ("".join(f" ({fact})" for fact in thing["facts"]))

    lines = []
    if view["location"]:
        lines += [f"Location: {line(view['location'])}",
                  "Exits: " + ("; ".join(f"{x['to']} via {x['label']}" for x in view["exits"]) or "none"),
                  "Here:" + ("".join(f"\n- {line(t)}" for t in view["here"]) or " nothing else")]
    skills = ", ".join(f"{name} {bonus:+d}" for name, bonus in view["character"]["skills"].items())
    lines += [f"You: {line(view['character'])}"] + ([f"Skills: {skills}"] if skills else [])
    lines.append("Carrying: " + (", ".join(t["name"] for t in view["carrying"]) or "nothing"))
    return "\n".join(lines)


async def show_state(session: Session, out: Show, perspective: str = "player") -> None:
    """Prints the player's view, or (dev role only) the GM's."""
    command = GetPlayerView() if perspective == "player" else GetState(perspective)
    view = next(e for e in await collect(session.send(command)) if isinstance(e, StateView))
    out((format_player_view(view.data) if view.perspective == "player" else "\n".join(view.data.values())) + "\n")


async def show_story(session: Session, out: Show) -> None:
    """Replays the story so far, for a game that was already begun."""
    view = next(e for e in await collect(session.send(GetPlayerView())) if isinstance(e, StateView))
    for part in view.data["story"]:
        format_message = format_player_message if part["speaker"] == "player" else format_assistant_message
        out(format_message(part["text"]), end="")


async def play(session: Session, ask: Ask = ask_input, out: Show = show, opening: bool = True) -> None:
    """Runs the game until the player quits.

    Args:
        session: The API session to play through.
        ask: Reads a line from the player.
        out: Writes text.
        opening: Whether to narrate the opening scene first.
    """
    dev = session.role is Role.DEV
    out(colorize("Type what you do. /state shows your situation" + (", /state gm the GM's view" if dev else "")
                 + ", /quit leaves.\n", "muted"))
    try:
        if opening:
            await run_turn(session, OpenScene(), ask, out)
        else:
            await show_story(session, out)
        while True:
            try:
                text = (await ask(colorize("> ", "player"))).strip()
            except (EOFError, KeyboardInterrupt):
                text = "/quit"  # Ctrl+C and end of input leave the same way /quit does
            if text in ("/quit", "/exit"):
                await collect(session.send(Quit()))
                break
            if text == "/state":
                await show_state(session, out)
            elif text == "/state gm" and dev:
                await show_state(session, out, "gm")
            elif text.startswith("/"):
                out(colorize(f"Unknown command {text.split()[0]}.\n", "muted"))
            elif text:
                await run_turn(session, SubmitAction(text), ask, out)
    except (EOFError, KeyboardInterrupt):  # interrupted while the storyteller was working or at a roll prompt
        pass
    await session.close()


def _open_world(path: Path) -> tuple[WorldStore, str, bool]:
    """Opens the world file, filling it with the demo world if it is new.

    Returns:
        The store, the player's entity id, and whether the story has already begun.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    store = WorldStore.open(path)
    if not store.find(kind="character"):
        return store, create_demo_world(store), False
    player = next(e for e in store.find(kind="character") if e.data.get("player"))
    return store, player.id, bool(store.events(kind="llm.call"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for ``python -m aimaginarium`` and the ``aimaginarium`` command."""
    parser = argparse.ArgumentParser(description="Play AImaginarium in the terminal.")
    parser.add_argument("--config", help="path to the TOML configuration (default: aimaginarium.toml)")
    parser.add_argument("--world", default="worlds/demo.sqlite", help="world database file (created if missing)")
    parser.add_argument("--dev", action="store_true", help="connect with the dev role (GM view, trace)")
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        llm = factory_from_file(
            args.config,
            on_retry=lambda n: print(f"[the storyteller is busy; retrying in {n.delay:.0f}s]", file=sys.stderr),
            on_fallback=lambda n: print(f"[{n.failed} is unavailable; trying {n.next}]", file=sys.stderr),
        )
    except ConfigError as exc:
        print(f"configuration problem: {exc}", file=sys.stderr)
        return 2
    store, player_id, begun = _open_world(Path(args.world))
    try:
        game = Game(store, llm, PromptBuilder.from_directory(), player_id)
        session = LocalServer(game, dev_enabled=args.dev).connect(Role.DEV if args.dev else Role.PLAYER)
        asyncio.run(play(session, opening=not begun))
    except ConfigError as exc:
        print(f"configuration problem: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        store.close()
    return 0
