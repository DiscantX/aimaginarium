"""Plain data types returned by the world store."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Fact:
    """Something the story has established about an entity.

    ``known_by`` is ``None`` for a public fact. For a restricted fact it lists
    the characters (or groups) that know it directly; an empty tuple means the
    GM only.
    """

    id: str
    entity_id: str
    text: str
    visibility: str
    created_seq: int
    superseded_seq: Optional[int] = None
    known_by: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    name: str
    parent_id: Optional[str]
    data: dict[str, Any]
    created_seq: int
    updated_seq: int
    removed_seq: Optional[int] = None
    established: tuple[Fact, ...] = ()


@dataclass(frozen=True)
class Event:
    seq: int
    turn_id: Optional[int]
    actor_id: str
    kind: str
    world_time: Optional[int]
    payload: dict[str, Any]
    causes: tuple[int, ...]
    created_at: str


@dataclass(frozen=True)
class CommitResult:
    events: tuple[Event, ...]
    refs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeError:
    index: int
    code: str
    message: str


class CommitError(Exception):
    """A commit was rejected and nothing was written."""

    def __init__(self, errors: list[ChangeError]):
        self.errors = errors
        super().__init__("; ".join(f"change {e.index}: {e.code}: {e.message}" for e in errors))

    def to_dict(self) -> dict[str, Any]:
        """Structured form, suitable for giving back to the LLM to retry."""
        return {
            "rejected": True,
            "errors": [{"change": e.index, "code": e.code, "message": e.message} for e in self.errors],
        }


class UndoError(Exception):
    """A turn cannot be taken back (it does not exist, or it is not the latest one)."""


class Rejected(Exception):
    """Raised while planning one change; becomes a ChangeError."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
