"""The in-process server: the API contract served directly over one :class:`~aimaginarium.engine.Game`.

Every client in the same process (the terminal now, the Textual UI later) talks
to this. It turns engine events into API events, keeps the session's event log
so ``subscribe`` can replay and follow it, and runs one command at a time.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from .. import engine as eng
from ..engine import Game, render_player_view, render_state
from ..trace import TraceRecord
from .commands import Command, GetPlayerView, GetState, GetTrace, OpenScene, Quit, Roll, SubmitAction, Undo
from .events import (
    ApiEvent, ChangesRejected, CheckCalled, CommandRejected, Done, Envelope, Narration, Repairing, ReplyUnreadable,
    RollResult, StateChanged, StateView, TraceEvent, TurnRetracted,
)
from .roles import Role, RoleError

def player_view(game: Game) -> dict[str, Any]:
    """Returns the player's view of the world plus the story so far."""
    story = [{"speaker": "player" if m.role == "user" else "narrator", "text": m.content} for m in game.history]
    return {**render_player_view(game.store, game.player_id), "story": story}


class LocalServer:
    """Serves one game to any number of in-process sessions."""

    def __init__(self, game: Game, dev_enabled: bool = False):
        """Initialises the server.

        Args:
            game: The game to serve.
            dev_enabled: Whether the dev role may connect (config decides).
        """
        self.game = game
        self.dev_enabled = dev_enabled
        self._log: list[Envelope] = []
        self._lock = asyncio.Lock()
        self._waiters: list[asyncio.Future] = []
        self._turn: Optional[int] = None
        if dev_enabled:  # trace goes into the log only when someone may see it
            game.tracer.add_sink(self._on_trace)

    def connect(self, role: Role = Role.PLAYER) -> "LocalSession":
        """Opens a session.

        Raises:
            RoleError: If the dev role is requested while it is disabled.
        """
        if role is Role.DEV and not self.dev_enabled:
            raise RoleError("the dev role is disabled")
        return LocalSession(self, role)

    # -- the event log ---------------------------------------------------

    def _on_trace(self, record: TraceRecord) -> None:
        """Puts a trace record into the log, for dev subscribers."""
        self._emit(self._trace_event(record), record.turn_id)

    @staticmethod
    def _trace_event(record: TraceRecord) -> TraceEvent:
        return TraceEvent(record.kind, record.payload, record.seq, record.at, record.turn_id)

    def _emit(self, event: ApiEvent, turn_id: Optional[int] = None) -> Envelope:
        """Appends an event to the log, wakes subscribers and returns its envelope."""
        envelope = Envelope(len(self._log) + 1, self._turn if turn_id is None else turn_id, event)
        self._log.append(envelope)
        self._wake()
        return envelope

    def _wake(self) -> None:
        waiters, self._waiters = self._waiters, []
        for future in waiters:
            if not future.done():
                future.set_result(None)

    async def _changed(self) -> None:
        """Waits until something is logged or a session closes."""
        future = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        await future

    # -- handling commands -----------------------------------------------

    async def handle(self, role: Role, command: Command) -> AsyncIterator[Envelope]:
        """Runs one command and streams the envelopes ``role`` may see; commands run one at a time."""
        async with self._lock:
            self._turn = None
            async for event in self._run(command):
                seen = self._emit(event).for_role(role)
                if seen is not None:
                    yield seen

    def _run(self, command: Command) -> AsyncIterator[ApiEvent]:
        game = self.game
        if isinstance(command, OpenScene):
            if game.begun:
                return self._rejected("already_begun", "The story has already begun.")
            return self._turn_events(game.open_scene())
        if isinstance(command, SubmitAction):
            if game.awaiting_roll:
                return self._rejected("awaiting_roll", "A check is waiting for its roll.")
            return self._turn_events(game.take_turn(game.player_id, command.text))
        if isinstance(command, Roll):
            if not game.awaiting_roll:
                return self._rejected("not_awaiting_roll", "No check is waiting for a roll.")
            return self._turn_events(game.resolve_check())
        if isinstance(command, GetPlayerView):
            return self._single(StateView("player", player_view(game)))
        if isinstance(command, GetState):
            if command.perspective == "player":
                return self._single(StateView("player", player_view(game)))
            return self._single(StateView("gm", render_state(game.store, game.player_id)))
        if isinstance(command, Undo):
            return self._undo()
        if isinstance(command, GetTrace):
            records = game.tracer.records(command.since, command.limit, command.turn)
            return self._single(*(self._trace_event(r) for r in records))
        if isinstance(command, Quit):
            return self._single()
        return self._rejected("not_available", f"{command.name} is not available.")

    async def _single(self, *events: ApiEvent) -> AsyncIterator[ApiEvent]:
        for event in events:
            yield event
        yield Done()

    async def _undo(self) -> AsyncIterator[ApiEvent]:
        turn = self.game.undo()
        if turn is None:
            yield CommandRejected("nothing_to_undo", "There is no turn to take back.")
        else:
            self._turn = turn
            yield TurnRetracted(turn)
            yield StateChanged()
        yield Done()

    def _rejected(self, code: str, message: str) -> AsyncIterator[ApiEvent]:
        return self._single(CommandRejected(code, message))

    async def _turn_events(self, source: AsyncIterator[Any]) -> AsyncIterator[ApiEvent]:
        """Translates a turn's engine events, then closes the reply with ``Done``."""
        async for item in source:
            self._turn = self.game.turn_id
            yield self._translate(item)
        self._turn = self.game.turn_id
        yield Done(self.game.turn_id, self.game.awaiting_roll)

    @staticmethod
    def _translate(item: Any) -> ApiEvent:
        """Turns one engine event into its API event."""
        if isinstance(item, eng.Narration):
            return Narration(item.text)
        if isinstance(item, eng.CheckCalled):
            workings = {"tier": item.ruling.tier, **item.ruling.as_payload()}
            return CheckCalled(item.roll.skill, item.roll.difficulty, item.reason, workings)
        if isinstance(item, eng.Rolled):
            r = item.roll
            return RollResult(r.skill, r.die, r.modifier, r.total, r.difficulty)
        if isinstance(item, eng.Committed):
            return StateChanged(tuple({"seq": e.seq, "kind": e.kind, "payload": e.payload} for e in item.events))
        if isinstance(item, eng.Repairing):
            return Repairing()
        if isinstance(item, eng.ChangesRejected):
            return ChangesRejected(tuple(e.message for e in item.errors))
        if isinstance(item, eng.ReplyUnreadable):
            return ReplyUnreadable(item.reason)
        raise TypeError(f"no API event for {type(item).__name__}")


class LocalSession:
    """One client's connection to a :class:`LocalServer`, fixed to one role."""

    def __init__(self, server: LocalServer, role: Role):
        self.role = role
        self._server = server
        self._closed = False

    def send(self, command: Command) -> AsyncIterator[Envelope]:
        """Sends a command and streams its reply, ending with ``Done``.

        Raises:
            RoleError: If this session's role may not send the command.
            RuntimeError: If the session is closed.
        """
        if self._closed:
            raise RuntimeError("the session is closed")
        command.check(self.role)
        return self._stream(command)

    async def _stream(self, command: Command) -> AsyncIterator[Envelope]:
        async for envelope in self._server.handle(self.role, command):
            yield envelope
        if isinstance(command, Quit):
            await self.close()

    async def subscribe(self, since: int = 0) -> AsyncIterator[Envelope]:
        """Streams every envelope this role may see after sequence ``since``, as it happens, until the session closes."""
        index = since
        while not self._closed:
            while index < len(self._server._log):
                seen = self._server._log[index].for_role(self.role)
                index += 1
                if seen is not None:
                    yield seen
            if not self._closed:
                await self._server._changed()

    async def close(self) -> None:
        """Ends the session and any subscription on it."""
        self._closed = True
        self._server._wake()
