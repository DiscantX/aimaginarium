"""Terminal client.

TEMPORARY: it calls :class:`aimaginarium.engine.Game` directly, in the same
process. Once the internal API exists, this client will talk to the API instead
and nothing else here should need to change.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Awaitable, Callable, Optional, Sequence

from dotenv import load_dotenv

from .engine import (
    ChangesRejected, CheckCalled, Game, Narration, PLAYER_ID, ReplyUnreadable, create_demo_world, render_state,
)
from .llm import ConfigError, FallbackNotice, RetryNotice, factory_from_file
from .prompts import PromptBuilder
from .world import WorldStore

Ask = Callable[[str], Awaitable[str]]
Show = Callable[..., None]


async def ask_input(prompt: str) -> str:
    """Reads a line without blocking the event loop."""
    return await asyncio.to_thread(input, prompt)


def show(text: str = "", end: str = "\n") -> None:
    """Prints and flushes, wrapping text cleanly to terminal width."""
    if text and end == "\n":
        term_width = shutil.get_terminal_size().columns
        text = textwrap.fill(text, width=term_width, break_long_words=False)
    print(text, end=end, flush=True)


async def render_turn(events, ask: Ask, out: Show) -> None:
    """Shows one turn's events, pausing for the player's roll.

    Args:
        events: The turn's event stream from :class:`Game`.
        ask: Reads a line from the player.
        out: Writes text.
    """
    async for event in events:
        if isinstance(event, Narration):
            out(event.text, end="")
        elif isinstance(event, CheckCalled):
            out()
            await ask(f"\n[{event.roll.skill.title()} check] Press Enter to roll... ")
            roll = event.roll
            out(f"You rolled {roll.die} {roll.modifier:+d} = {roll.total}.\n")
        elif isinstance(event, ChangesRejected):
            out(f"\n\n[Some changes were not accepted: {event.errors[0].message}. The world is unchanged.]", end="")
        elif isinstance(event, ReplyUnreadable):
            out(f"\n\n[{event.reason}]", end="")
    out("\n")


async def play(game: Game, ask: Ask = ask_input, out: Show = show, opening: bool = True) -> None:
    """Runs the game until the player quits.

    Args:
        game: The game to play.
        ask: Reads a line from the player.
        out: Writes text.
        opening: Whether to narrate the opening scene first.
    """
    out("Type what you do. /state shows what the narrator sees, /quit leaves.\n")
    if opening:
        await render_turn(game.open_scene(), ask, out)
    else:
        for msg in game._history:
            if msg.role == "user":
                out(f"> {msg.content}")
            elif msg.role == "assistant":
                out(msg.content)
                out()
    while True:
        try:
            text = (await ask("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("/quit", "/exit"):
            break
        if text == "/state":
            out("\n".join(render_state(game.store, game.player_id).values()) + "\n")
        elif text:
            await render_turn(game.take_turn(game.player_id, text), ask, out)


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
        asyncio.run(play(Game(store, llm, PromptBuilder.from_directory(), player_id), opening=not begun))
    except ConfigError as exc:
        print(f"configuration problem: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
    return 0
