"""Commands: everything a client can send to the server.

There are two input paths. The **player path** is the game itself: opening the
scene, describing an action in prose, and rolling when a check is called. There
are no in-game verbs, so nothing here ever names an action the character can
take. The **system path** is out-of-character: views, undo, trace and leaving.
Slash commands and the command palette map onto the system path only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Mapping

from .roles import Role, RoleError


class InputPath(str, Enum):
    """Whether a command is part of the game or outside it."""

    PLAYER = "player"
    SYSTEM = "system"


_REGISTRY: dict[str, type["Command"]] = {}


def command(name: str):
    """Class decorator that registers a command under its wire name."""

    def register(cls: type["Command"]) -> type["Command"]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return register


@dataclass(frozen=True)
class Command:
    """Base class of every command.

    Attributes:
        name: The wire name (set by :func:`command`).
        path: Which input path the command belongs to.
        roles: The roles allowed to send it.
    """

    name: ClassVar[str]
    path: ClassVar[InputPath] = InputPath.SYSTEM
    roles: ClassVar[frozenset[Role]] = frozenset(Role)

    def check(self, role: Role) -> None:
        """Raises :class:`RoleError` if ``role`` may not send this command."""
        if role not in self.roles:
            raise RoleError(f"the {role.value} role may not send {self.name!r}")

    def to_dict(self) -> dict[str, Any]:
        """Returns the wire form: ``{"command": name, ...fields}``."""
        return {"command": self.name, **asdict(self)}


@command("open_scene")
@dataclass(frozen=True)
class OpenScene(Command):
    """Narrates the opening of the story. Sent once, before the first action."""

    path: ClassVar[InputPath] = InputPath.PLAYER


@command("submit_action")
@dataclass(frozen=True)
class SubmitAction(Command):
    """The player says or does something, in plain prose.

    Attributes:
        text: What the player does or says.
    """

    path: ClassVar[InputPath] = InputPath.PLAYER
    text: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("an action needs some text")


@command("roll")
@dataclass(frozen=True)
class Roll(Command):
    """The player rolls the die for a check that was called.

    This is the only way a turn resumes after :class:`~.events.CheckCalled`: the
    turn stream ends with ``Done(awaiting_roll=True)`` and continues when this
    command arrives. The roll itself was fixed in advance; sending the command
    reveals it.
    """

    path: ClassVar[InputPath] = InputPath.PLAYER


@command("get_player_view")
@dataclass(frozen=True)
class GetPlayerView(Command):
    """Asks for the world as the player's character knows it (a projection)."""


@command("quit")
@dataclass(frozen=True)
class Quit(Command):
    """Ends the session. Nothing is lost: the world is saved after every turn."""


@command("undo")
@dataclass(frozen=True)
class Undo(Command):
    """Takes back the latest turn (dev only; whether players get it is open)."""

    roles: ClassVar[frozenset[Role]] = frozenset({Role.DEV})


@command("get_state")
@dataclass(frozen=True)
class GetState(Command):
    """Asks for the world state (dev only).

    Attributes:
        perspective: ``"gm"`` for everything, or ``"player"`` for the projection.
    """

    roles: ClassVar[frozenset[Role]] = frozenset({Role.DEV})
    perspective: str = "gm"

    def __post_init__(self) -> None:
        if self.perspective not in ("gm", "player"):
            raise ValueError("perspective must be 'gm' or 'player'")


@command("get_trace")
@dataclass(frozen=True)
class GetTrace(Command):
    """Asks for recorded trace events (dev only).

    Attributes:
        since: Return only events after this sequence number.
        limit: Most events to return.
    """

    roles: ClassVar[frozenset[Role]] = frozenset({Role.DEV})
    since: int = 0
    limit: int = 200

    def __post_init__(self) -> None:
        if self.since < 0 or self.limit < 1:
            raise ValueError("since must be 0 or more and limit at least 1")


def parse_command(data: Mapping[str, Any]) -> Command:
    """Builds a command from its wire form.

    Args:
        data: ``{"command": name, ...fields}``, as produced by :meth:`Command.to_dict`.

    Returns:
        The command.

    Raises:
        ValueError: If the command is unknown or its fields are wrong.
    """
    name = data.get("command")
    cls = _REGISTRY.get(name) if isinstance(name, str) else None
    if cls is None:
        raise ValueError(f"unknown command {name!r}")
    allowed = {f.name for f in fields(cls)}
    extra = set(data) - allowed - {"command"}
    if extra:
        raise ValueError(f"{name}: unexpected fields {sorted(extra)}")
    try:
        return cls(**{k: v for k, v in data.items() if k != "command"})
    except TypeError as exc:
        raise ValueError(f"{name}: {exc}") from exc
