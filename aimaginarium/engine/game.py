"""The game: turns, checks and commits, on top of the world store and the LLM gateway.

Clients do not call :class:`Game` directly; they talk to a server from
:mod:`aimaginarium.api`, which turns the engine events below into API events.

A turn is a stream of events. A check splits it in two: ``take_turn`` ends
with :class:`CheckCalled` and the game waits (:attr:`Game.awaiting_roll`) until
:meth:`Game.resolve_check` is called, which reveals the roll and plays the rest.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Optional, Union

from pydantic import BaseModel, ValidationError

from ..llm import (
    Chunk, Message, ProviderError, ProviderFactory, Request, Response, StructuredOutputError, narration_events,
)
from ..llm.structured import strip_fences
from ..prompts import Prompt, PromptBuilder
from ..world import ChangeError, CommitError, Event, Record, WorldStore
from .replies import CheckRequest, OutcomeReply, RepairReply, TurnReply
from .rules import D20Rules, Roll, Ruling
from .view import render_state

GM = "gm"
ENGINE = "engine"


@dataclass(frozen=True)
class Narration:
    """A piece of narration to show the player as it arrives."""

    text: str


@dataclass(frozen=True)
class CheckCalled:
    """A dice check was called for; the turn pauses until :meth:`Game.resolve_check`.

    Attributes:
        roll: The precomputed roll. Clients show only the difficulty until
            :class:`Rolled` reveals the numbers.
        reason: Why the check matters.
        ruling: How the difficulty was worked out (tier and factors), for
            clients that show their workings, such as a developer panel.
    """

    roll: Roll
    reason: str
    ruling: Ruling


@dataclass(frozen=True)
class Rolled:
    """The player rolled for the pending check; ``roll`` is now revealed."""

    roll: Roll


@dataclass(frozen=True)
class Committed:
    """The world changes that were validated and committed."""

    events: tuple[Event, ...]


@dataclass(frozen=True)
class Repairing:
    """The proposed changes were rejected; the narrator is being asked to correct them."""


@dataclass(frozen=True)
class ChangesRejected:
    """The proposed changes failed validation; nothing was committed."""

    errors: tuple[ChangeError, ...]


@dataclass(frozen=True)
class ReplyUnreadable:
    """The model's reply could not be read; the world is unchanged."""

    reason: str


TurnEvent = Union[Narration, CheckCalled, Rolled, Committed, Repairing, ChangesRejected, ReplyUnreadable]


@dataclass(frozen=True)
class _Pending:
    """Internal: a turn paused at a check, waiting for the player's roll."""

    turn: int
    text: str
    state: dict[str, str]
    request: Request
    first: "_Reply"
    check: CheckRequest
    requested: Event
    roll: Roll


@dataclass(frozen=True)
class _Reply:
    """Internal: a finished model call."""

    narration: str
    parsed: Any
    response: Response


class Game:
    """One player's game in one world."""

    def __init__(
        self,
        store: WorldStore,
        llm: ProviderFactory,
        prompts: PromptBuilder,
        player_id: str,
        rules: Optional[D20Rules] = None,
        history_limit: int = 12,
    ):
        """Initialises the game.

        Args:
            store: The world.
            llm: Chooses a provider and model per task.
            prompts: Builds the prompts.
            player_id: Entity id of the player's character.
            rules: Dice and classification; defaults to :class:`D20Rules`.
            history_limit: Most past messages sent to the model.
        """
        self.store, self.llm, self.prompts = store, llm, prompts
        self.player_id = player_id
        self.rules = rules or D20Rules()
        self.history_limit = history_limit
        self._history: list[Message] = self._load_history()
        self._pending: Optional[_Pending] = None
        self.turn_id: Optional[int] = None

    @property
    def awaiting_roll(self) -> bool:
        """Whether a check has been called and is waiting for :meth:`resolve_check`."""
        return self._pending is not None

    @property
    def begun(self) -> bool:
        """Whether the story has already been opened."""
        return bool(self.store.events(kind="llm.call"))

    @property
    def history(self) -> list[Message]:
        """The conversation so far: the player's words and the narration, oldest first."""
        return list(self._history)

    def _load_history(self) -> list[Message]:
        """Loads past conversation history from the store's event log."""
        events = self.store.events()
        turns: dict[int, dict[str, str]] = {}
        for ev in events:
            if ev.kind == "player.action":
                turns.setdefault(ev.turn_id, {})["player"] = ev.payload.get("text", "")
            elif ev.kind == "llm.call" and "narration" in ev.payload:
                turn = turns.setdefault(ev.turn_id, {})
                turn["narration"] = "\n\n".join(filter(None, [turn.get("narration"), ev.payload["narration"]]))

        history: list[Message] = []
        for turn_id in sorted(turns.keys()):
            t = turns[turn_id]
            if "narration" in t:
                player_text = t.get("player", "(The story begins.)")
                history.append(Message("user", player_text))
                history.append(Message("assistant", t["narration"]))
        return history

    async def open_scene(self) -> AsyncIterator[TurnEvent]:
        """Narrates the opening of the story (call this once, before the first turn)."""
        turn = self.turn_id = self.store.new_turn()
        prompt = self.prompts.build("opening", state=render_state(self.store, self.player_id))
        request = prompt.request(schema=TurnReply)
        reply = None
        async for item in self._call(prompt, request, TurnReply, turn):
            if isinstance(item, _Reply):
                reply = item
            else:
                yield item
        if reply is None:
            return
        async for event in self._commit(reply.parsed.changes, turn, [], reply.narration):
            yield event
        self._remember("(The story begins.)", reply.narration)

    async def take_turn(self, actor: str, text: str) -> AsyncIterator[TurnEvent]:
        """Plays one turn: the player's action, then what happens.

        Args:
            actor: The acting character's id; must be the player's character.
            text: What the player does or says.

        Yields:
            Narration as it streams, then either the commit result or, if a roll
            is needed, a :class:`CheckCalled` that ends the stream. Call
            :meth:`resolve_check` to continue.

        Raises:
            ValueError: If ``actor`` is not the player's character.
            RuntimeError: If a check is still waiting for its roll.
        """
        if actor != self.player_id:
            raise ValueError(f"{actor!r} is not the player's character")
        if self._pending:
            raise RuntimeError("a check is waiting for its roll")
        turn = self.turn_id = self.store.new_turn()
        action = self._record("player.action", actor, turn, {"text": text}, [], [actor])
        state = render_state(self.store, self.player_id)
        prompt = self.prompts.build("narrate", state=state)
        request = prompt.request(self._recent(), text, schema=TurnReply)
        first = None
        async for item in self._call(prompt, request, TurnReply, turn, [action.seq]):
            if isinstance(item, _Reply):
                first = item
            else:
                yield item
        if first is None:
            return
        check: Optional[CheckRequest] = first.parsed.check
        if check is None:
            async for event in self._commit(first.parsed.changes, turn, [action.seq], first.narration):
                yield event
            self._remember(text, first.narration)
            return

        ruling = self.rules.rule(check)
        requested = self._record("check.requested", GM, turn, {**check.model_dump(), **ruling.as_payload()},
                                 [action.seq], [actor])
        roll = self.rules.roll(self.store.get_entity(actor), check.skill, ruling.difficulty)
        self._pending = _Pending(turn, text, state, request, first, check, requested, roll)
        yield CheckCalled(roll, check.reason, ruling)

    async def resolve_check(self) -> AsyncIterator[TurnEvent]:
        """Reveals the pending roll and plays the rest of the turn.

        Yields:
            :class:`Rolled`, then narration as it streams, then the commit result.

        Raises:
            RuntimeError: If no check is waiting.
        """
        if self._pending is None:
            raise RuntimeError("no check is waiting for a roll")
        pending, self._pending = self._pending, None
        turn, roll, check, first = pending.turn, pending.roll, pending.check, pending.first
        self.turn_id = turn
        rolled = self._record("roll", self.player_id, turn, asdict(roll), [pending.requested.seq], [self.player_id])
        yield Rolled(roll)

        outcome = self.prompts.build("check_outcome", state={**pending.state, **self._roll_state(roll, check)})
        followup = outcome.request(
            [*pending.request.messages, Message("assistant", first.narration)], schema=OutcomeReply
        )
        second = None
        async for item in self._call(outcome, followup, OutcomeReply, turn, [rolled.seq]):
            if isinstance(item, _Reply):
                second = item
            else:
                yield item
        if second is None:
            return
        story = f"{first.narration}\n\n{second.narration}"
        async for event in self._commit(second.parsed.changes, turn, [rolled.seq], story):
            yield event
        self._remember(pending.text, story)

    # -- calling the model -----------------------------------------------

    async def _call(
        self, prompt: Prompt, request: Request, schema: type[BaseModel], turn: int, causes: Optional[list[int]] = None
    ) -> AsyncIterator[Union[Narration, _Reply, ReplyUnreadable]]:
        """Streams a call, yielding narration, then the parsed reply (or why it was unreadable)."""
        route = self.llm.route(prompt.task)
        final: Optional[Response] = None
        try:
            async for event in narration_events(route.stream(request)):
                if isinstance(event, Chunk):
                    yield Narration(event.text)
                elif isinstance(event, Response):
                    final = event
        except ProviderError as exc:
            self._record("llm.failed", ENGINE, turn, {**prompt.record(), "error": str(exc)}, causes or [])
            yield ReplyUnreadable(f"the storyteller could not be reached: {exc}")
            return
        try:
            data = json.loads(strip_fences(final.text))
            parts = data["narration"]
            narration = "\n\n".join(parts) if isinstance(parts, list) else str(parts)
            self._record("llm.call", ENGINE, turn, {**prompt.record(), "model": final.model, "usage": asdict(final.usage), "narration": narration},
                         causes or [])
            yield _Reply(narration, schema.model_validate(data), final)
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            self._record("llm.call", ENGINE, turn, {**prompt.record(), "model": final.model, "usage": asdict(final.usage)},
                         causes or [])
            self._record("reply.invalid", ENGINE, turn, {"error": str(exc)[:500], "text": final.text[:2000]}, causes or [])
            yield ReplyUnreadable(f"the reply could not be read: {exc}")

    # -- committing --------------------------------------------------------

    async def _commit(
        self, changes: list[dict[str, Any]], turn: int, causes: list[int], narration: str
    ) -> AsyncIterator[TurnEvent]:
        """Commits the proposed changes; if the store rejects them, asks once for a correction.

        A rejection writes nothing, so the world is never half-changed. The
        correction is a second proposal for the same story event, checked the same way.
        """
        if not changes:
            return
        result = self._try_commit(changes, turn, causes)
        if isinstance(result, tuple):
            yield Committed(result)
            return
        errors = result
        self._record("changes.rejected", ENGINE, turn, {"errors": [asdict(e) for e in errors], "changes": changes}, causes)
        yield Repairing()
        fixed = await self._repair(changes, errors, narration, turn, causes)
        if fixed:
            result = self._try_commit(fixed, turn, causes)
            if isinstance(result, tuple):
                yield Committed(result)
                return
            self._record("changes.rejected", ENGINE, turn,
                         {"errors": [asdict(e) for e in result], "changes": fixed, "repaired": True}, causes)
            errors = result
        yield ChangesRejected(tuple(errors))

    def _try_commit(
        self, changes: list[dict[str, Any]], turn: int, causes: list[int]
    ) -> Union[tuple[Event, ...], list[ChangeError]]:
        """Returns the committed events (a tuple), or the errors (a list) if the store rejected the changes."""
        try:
            return self.store.commit(changes, actor=GM, turn=turn, causes=causes).events
        except CommitError as exc:
            return list(exc.errors)

    async def _repair(
        self, changes: list[dict[str, Any]], errors: list[ChangeError], narration: str, turn: int, causes: list[int]
    ) -> Optional[list[dict[str, Any]]]:
        """Asks the narrator for corrected changes; returns None if it cannot give any."""
        values = {
            **render_state(self.store, self.player_id),
            "narration": narration,
            "changes": json.dumps(changes, indent=2),
            "errors": "\n".join(f"- change {e.index}: {e.message} ({e.code})" for e in errors),
        }
        prompt = self.prompts.build("repair", state=values)
        try:
            parsed, response = await self.llm.route(prompt.task).call(prompt.request(schema=RepairReply), RepairReply)
        except (ProviderError, StructuredOutputError) as exc:
            self._record("llm.failed", ENGINE, turn, {**prompt.record(), "error": str(exc)}, causes)
            return None
        self._record("llm.call", ENGINE, turn,
                     {**prompt.record(), "model": response.model, "usage": asdict(response.usage)}, causes)
        return parsed.changes

    def _record(self, kind: str, actor: str, turn: int, payload: dict[str, Any], causes: list[int],
                entities: Optional[list[str]] = None) -> Event:
        """Logs something that changes no state."""
        change = Record(kind=kind, payload=payload, entities=entities or [])
        return self.store.commit([change], actor=actor, turn=turn, causes=causes).events[0]

    # -- conversation ------------------------------------------------------

    @staticmethod
    def _roll_state(roll: Roll, check: CheckRequest) -> dict[str, Any]:
        """Values for the state fragments of the outcome prompt."""
        return {"roll": roll.die, "skill": roll.skill, "difficulty": roll.difficulty, "margin": roll.margin,
                "classification": roll.classification, "tier": check.tier.replace("_", " ")}

    def _recent(self) -> list[Message]:
        """Returns the most recent history, starting on a player message."""
        recent = self._history[-self.history_limit:]
        return recent[1:] if recent and recent[0].role == "assistant" else recent

    def _remember(self, player_text: str, narration: str) -> None:
        """Keeps the player's words and the narration, without the per-call world state."""
        self._history += [Message("user", player_text), Message("assistant", narration)]
