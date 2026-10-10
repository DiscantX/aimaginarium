"""Startup shared by every local client: arguments, config, world, tracer and API session."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from ..api import LocalServer, Role, Session
from ..engine import Game, create_demo_world
from ..llm import FallbackNotice, RetryNotice, factory_from_file
from ..prompts import PromptBuilder
from ..devstore import DevStore
from ..trace import JsonlSink, Tracer
from ..world import WorldStore

Notify = Callable[[str], None]


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the options every local client accepts."""
    parser.add_argument("--config", help="path to the TOML configuration (default: aimaginarium.toml)")
    parser.add_argument("--world", default="worlds/demo.sqlite", help="world database file (created if missing)")
    parser.add_argument("--dev", action="store_true", help="connect with the dev role (GM view, trace)")
    parser.add_argument("--trace", help="append the trace (prompts, replies, timings, checks) to this JSON-lines file")
    parser.add_argument("--dev-store", help="the dev store file: dev notes and the full trace of every world played "
                                            "with --dev (default: dev.sqlite beside the world file)")


def _notify_stderr(text: str) -> None:
    print(text, file=sys.stderr)


def open_world(path: Path) -> tuple[WorldStore, str, bool]:
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


@dataclass
class Runtime:
    """An open game and the API session a client plays through.

    Attributes:
        session: The API session, in the role the arguments asked for.
        begun: Whether the story had already begun when the world was opened.
    """

    session: Session
    begun: bool
    _tracer: Tracer
    _store: WorldStore
    _devstore: Optional[DevStore] = None

    @classmethod
    def open(cls, args: argparse.Namespace, notify: Notify = _notify_stderr) -> "Runtime":
        """Loads the environment, config and world, and connects a session.

        Args:
            args: Parsed arguments from a parser given :func:`add_common_arguments`.
            notify: Receives short status lines (retries, fallbacks) for the client to show.

        Raises:
            ConfigError: If the configuration is missing or invalid.
        """
        load_dotenv()
        tracer = Tracer()
        if args.trace:
            tracer.add_sink(JsonlSink(Path(args.trace)))

        def retrying(notice: RetryNotice) -> None:
            notify(f"[the storyteller is busy; retrying in {notice.delay:.0f}s]")
            tracer.on_retry(notice)

        def falling_back(notice: FallbackNotice) -> None:
            notify(f"[{notice.failed} is unavailable; trying {notice.next}]")
            tracer.on_fallback(notice)

        try:
            llm = factory_from_file(args.config, on_retry=retrying, on_fallback=falling_back)
            store, player_id, begun = open_world(Path(args.world))
        except BaseException:
            tracer.close()
            raise
        try:
            devstore = None
            if args.dev:                                  # the full trace and the notes are for the dev role only
                devstore = DevStore.open(args.dev_store or Path(args.world).parent / "dev.sqlite")
                tracer.add_sink(devstore.trace_sink(store.world_id))
            game = Game(store, llm, PromptBuilder.from_directory(), player_id, tracer=tracer)
            role = Role.DEV if args.dev else Role.PLAYER
            session = LocalServer(game, dev_enabled=args.dev, devstore=devstore).connect(role)
        except BaseException:
            tracer.close()
            store.close()
            if devstore is not None:
                devstore.close()
            raise
        return cls(session, begun, tracer, store, devstore)

    def close(self) -> None:
        """Flushes the trace and closes the world file."""
        self._tracer.close()
        self._store.close()
        if self._devstore is not None:
            self._devstore.close()
