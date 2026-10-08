"""Events: everything the server sends back.

Every event class says which roles may see it, and any field that only the dev
role may see is marked with :func:`dev_only`. :meth:`ApiEvent.for_role` is the
one place that strips them, so the server cannot forget to, and a player client
never receives hidden state (tenet 4).

A command's reply is a finite stream that always ends with :class:`Done`.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields, replace
from typing import Any, ClassVar, Optional

from .roles import Role


def dev_only(default: Any = None):
    """Declares a dataclass field only the dev role receives; others get ``default``."""
    return field(default=default, metadata={"dev_only": True})


@dataclass(frozen=True)
class ApiEvent:
    """Base class of every event.

    Attributes:
        name: The wire name (the class name in snake case).
        roles: The roles that may see the event at all.
    """

    name: ClassVar[str]
    roles: ClassVar[frozenset[Role]] = frozenset(Role)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.name = "".join(f"_{c.lower()}" if c.isupper() else c for c in cls.__name__).lstrip("_")

    def for_role(self, role: Role) -> Optional["ApiEvent"]:
        """Returns what ``role`` may see of this event, or None if it may see none of it."""
        if role not in self.roles:
            return None
        if role is Role.DEV:
            return self
        hidden = {f.name: f.default for f in fields(self) if f.metadata.get("dev_only")}
        return replace(self, **hidden) if hidden else self

    def to_dict(self) -> dict[str, Any]:
        """Returns the wire form: ``{"type": name, ...fields}``."""
        return {"type": self.name, **asdict(self)}


@dataclass(frozen=True)
class Narration(ApiEvent):
    """A piece of narration, as it streams."""

    text: str


@dataclass(frozen=True)
class CheckCalled(ApiEvent):
    """A check was called for; the turn is paused until the client sends ``Roll``.

    Attributes:
        skill: What is being tested.
        difficulty: The number the total must meet (the player sees it).
        reason: Why the check matters (dev only: it is the GM's reasoning).
        workings: Tier, factors and how the difficulty was reached (dev only).
    """

    skill: str
    difficulty: int
    reason: str = dev_only("")
    workings: Optional[dict] = dev_only(None)


@dataclass(frozen=True)
class RollResult(ApiEvent):
    """The revealed roll, sent in reply to ``Roll``.

    Attributes:
        classification: The engine's ruling on the roll: ``critical_failure``, ``failure``, ``narrow_success``,
            ``success`` or ``critical_success``. Clients show this rather than judging the total themselves.
    """

    skill: str
    die: int
    modifier: int
    total: int
    difficulty: int
    classification: str = ""


@dataclass(frozen=True)
class Repairing(ApiEvent):
    """The proposed changes were rejected and the narrator is being asked to correct them."""


@dataclass(frozen=True)
class ChangesRejected(ApiEvent):
    """The proposed changes failed validation; nothing was committed.

    Attributes:
        errors: What was wrong (dev only: it can name hidden entities).
    """

    errors: tuple[str, ...] = dev_only(())


@dataclass(frozen=True)
class StateChanged(ApiEvent):
    """The world changed. Clients that show state re-query it.

    Attributes:
        changes: The committed changes (dev only: they are raw world state).
    """

    changes: tuple[dict, ...] = dev_only(())


@dataclass(frozen=True)
class ReplyUnreadable(ApiEvent):
    """The model's reply could not be used; the world is unchanged."""

    reason: str


@dataclass(frozen=True)
class CommandRejected(ApiEvent):
    """A command could not be carried out (wrong moment, nothing to undo, and so on).

    Attributes:
        code: A stable short code, such as ``"not_awaiting_roll"``.
        message: A sentence for a human.
    """

    code: str
    message: str


@dataclass(frozen=True)
class StateView(ApiEvent):
    """The world, in reply to ``GetPlayerView`` or ``GetState``.

    Attributes:
        perspective: ``"player"`` or ``"gm"``.
        data: The view; a ``"gm"`` view is only ever sent to the dev role.
    """

    perspective: str
    data: dict

    def for_role(self, role: Role) -> Optional["ApiEvent"]:
        return None if self.perspective == "gm" and role is not Role.DEV else self


@dataclass(frozen=True)
class TurnRetracted(ApiEvent):
    """A turn was undone; clients grey it out (dev) or drop it."""

    turn_id: int


@dataclass(frozen=True)
class TraceEvent(ApiEvent):
    """One thing the engine or an LLM call did behind the scenes (dev only).

    Attributes:
        kind: What it was, such as ``"llm.call"`` or ``"check.workings"``.
        payload: Its details.
        trace_seq: Its position in the trace (separate from the envelope ``seq``).
        at: When it happened, UTC, ISO 8601.
        turn_id: The turn it belongs to, if any.
    """

    roles: ClassVar[frozenset[Role]] = frozenset({Role.DEV})
    kind: str
    payload: dict
    trace_seq: int = 0
    at: str = ""
    turn_id: Optional[int] = None


@dataclass(frozen=True)
class Done(ApiEvent):
    """The last event of every reply stream.

    Attributes:
        turn_id: The turn this reply belonged to, if any.
        awaiting_roll: True when the turn is paused for a ``Roll`` command.
    """

    turn_id: Optional[int] = None
    awaiting_roll: bool = False


@dataclass(frozen=True)
class Envelope:
    """An event with its place in the stream.

    Attributes:
        seq: Position in the server's log, increasing by one. A role that may not
            see some events sees gaps where they were.
        turn_id: The turn the event belongs to, or None.
        event: The event.
    """

    seq: int
    turn_id: Optional[int]
    event: ApiEvent

    def for_role(self, role: Role) -> Optional["Envelope"]:
        """Returns the envelope as ``role`` may see it, or None if it may not see it."""
        seen = self.event.for_role(role)
        return None if seen is None else replace(self, event=seen)

    def to_dict(self) -> dict[str, Any]:
        """Returns the wire form."""
        return {"seq": self.seq, "turn_id": self.turn_id, "event": self.event.to_dict()}
