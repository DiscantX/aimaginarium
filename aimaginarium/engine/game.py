"""The game facade used by the terminal client.

TEMPORARY: this in-process class stands in for the internal API (see
wiki/tech/llm-gateway.md, "Layering"). Clients will talk to a real API layer
that calls the engine; until it exists, the terminal calls :class:`Game`
directly. Keep its surface small (``open_scene``, ``take_turn``), because that
is the boundary the API and the MCP servers will expose.

A turn is a stream of events. The client waits for the player by not asking
for the next event: after :class:`CheckCalled` the generator is suspended
until the client resumes it, which it does once the player has pressed the
roll button.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Optional, Union

from pydantic import BaseModel, ValidationError

from ..llm import Chunk, Message, ProviderError, ProviderFactory, Request, Response, narration_events
from ..llm.structured import strip_fences
from ..prompts import Prompt, PromptBuilder
from ..world import ChangeError, CommitError, Event, Record, WorldStore
from .replies import CheckRequest, OutcomeReply, TurnReply
from .rules import D20Rules, Roll
from .view import render_state

GM = "gm"
ENGINE = "engine"


@dataclass(frozen=True)
class Narration:
    """A piece of narration to show the player as it arrives."""

    text: str


@dataclass(frozen=True)
class CheckCalled:
    """A dice check was called for; the client lets the player roll, then resumes.

    Attributes:
        roll: The precomputed roll. The client shows ``die``, ``modifier`` and
            ``total`` when the player presses the button, and never the difficulty.
        reason: Why the check matters.
    """

    roll: Roll
    reason: str


@dataclass(frozen=True)
class Committed:
    """The world changes that were validated and committed."""

    events: tuple[Event, ...]


@dataclass(frozen=True)
class ChangesRejected:
    """The proposed changes failed validation; nothing was committed."""

    errors: tuple[ChangeError, ...]


@dataclass(frozen=True)
class ReplyUnreadable:
    """The model's reply could not be read; the world is unchanged."""

    reason: str


TurnEvent = Union[Narration, CheckCalled, Committed, ChangesRejected, ReplyUnreadable]


@dataclass(frozen=True)
class _Reply:
    """Internal: a finished model call."""

    narration: str
    parsed: Any
    response: Response


class Game:
    """One player's game in one world. TEMPORARY facade, see the module docstring."""

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

    def _load_history(self) -> list[Message]:
        """Loads past conversation history from the store's event log."""
        events = self.store.events()
        turns: dict[int, dict[str, str]] = {}
        for ev in events:
            if ev.kind == "player.action":
                turns.setdefault(ev.turn_id, {})["player"] = ev.payload.get("text", "")
            elif ev.kind == "llm.call" and "narration" in ev.payload:
                turns.setdefault(ev.turn_id, {})["narration"] = ev.payload.get("narration", "")

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
        turn = self.store.new_turn()
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
        for event in self._commit(reply.parsed.changes, turn, []):
            yield event
        self._remember("(The story begins.)", reply.narration)

    async def take_turn(self, actor: str, text: str) -> AsyncIterator[TurnEvent]:
        """Plays one turn: the player's action, then what happens.

        Args:
            actor: The acting character's id; must be the player's character.
            text: What the player does or says.

        Yields:
            Narration as it streams, a :class:`CheckCalled` if a roll is needed
            (resume to continue), then the commit result.

        Raises:
            ValueError: If ``actor`` is not the player's character.
        """
        if actor != self.player_id:
            raise ValueError(f"{actor!r} is not the player's character")
        turn = self.store.new_turn()
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
            for event in self._commit(first.parsed.changes, turn, [action.seq]):
                yield event
            self._remember(text, first.narration)
            return

        requested = self._record("check.requested", GM, turn, check.model_dump(), [action.seq], [actor])
        roll = self.rules.roll(self.store.get_entity(actor), check.skill, check.difficulty)
        yield CheckCalled(roll, check.reason)
        rolled = self._record("roll", actor, turn, asdict(roll), [requested.seq], [actor])

        outcome = self.prompts.build("check_outcome", state={**state, **self._roll_state(roll)})
        followup = outcome.request(
            [*request.messages, Message("assistant", first.narration)], schema=OutcomeReply
        )
        second = None
        async for item in self._call(outcome, followup, OutcomeReply, turn, [rolled.seq]):
            if isinstance(item, _Reply):
                second = item
            else:
                yield item
        if second is None:
            return
        for event in self._commit(second.parsed.changes, turn, [rolled.seq]):
            yield event
        self._remember(text, f"{first.narration}\n\n{second.narration}")

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

    def _commit(self, changes: list[dict[str, Any]], turn: int, causes: list[int]) -> list[TurnEvent]:
        """Validates and commits the proposed changes; a rejection leaves the world untouched."""
        if not changes:
            return []
        try:
            return [Committed(self.store.commit(changes, actor=GM, turn=turn, causes=causes).events)]
        except CommitError as exc:
            self._record("changes.rejected", ENGINE, turn,
                         {"errors": [asdict(e) for e in exc.errors], "changes": changes}, causes)
            return [ChangesRejected(tuple(exc.errors))]

    def _record(self, kind: str, actor: str, turn: int, payload: dict[str, Any], causes: list[int],
                entities: Optional[list[str]] = None) -> Event:
        """Logs something that changes no state."""
        change = Record(kind=kind, payload=payload, entities=entities or [])
        return self.store.commit([change], actor=actor, turn=turn, causes=causes).events[0]

    # -- conversation ------------------------------------------------------

    @staticmethod
    def _roll_state(roll: Roll) -> dict[str, Any]:
        """Values for the state fragments of the outcome prompt."""
        return {"roll": roll.die, "skill": roll.skill, "difficulty": roll.difficulty, "margin": roll.margin,
                "classification": roll.classification}

    def _recent(self) -> list[Message]:
        """Returns the most recent history, starting on a player message."""
        recent = self._history[-self.history_limit:]
        return recent[1:] if recent and recent[0].role == "assistant" else recent

    def _remember(self, player_text: str, narration: str) -> None:
        """Keeps the player's words and the narration, without the per-call world state."""
        self._history += [Message("user", player_text), Message("assistant", narration)]
