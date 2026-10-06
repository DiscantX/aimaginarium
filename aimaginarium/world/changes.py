"""What a commit may ask the world store to do.

Every change is a small Pydantic model, so an LLM's JSON proposal validates
straight into them with :func:`parse_changes`. Ids written as ``"@name"`` refer
to something created earlier in the same commit (see ``ref`` on Create and
Establish).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Change(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Create(_Change):
    """Create an entity. ``parent_id`` says where it is (a location, a character, a container)."""

    op: Literal["create"] = "create"
    kind: str
    name: str
    parent_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None
    ref: Optional[str] = None


class Update(_Change):
    """Rename an entity and/or set or unset values in its data (dotted paths, e.g. ``sheet.hp.current``)."""

    op: Literal["update"] = "update"
    entity: str
    name: Optional[str] = None
    set: dict[str, Any] = Field(default_factory=dict)
    unset: list[str] = Field(default_factory=list)


class Move(_Change):
    """Change an entity's parent (pick up an item, walk into a room)."""

    op: Literal["move"] = "move"
    entity: str
    to: Optional[str] = None


class Remove(_Change):
    """Remove an entity from the world (it stays in the log)."""

    op: Literal["remove"] = "remove"
    entity: str


class Establish(_Change):
    """Record a fact about an entity. ``known_by`` omitted means public; a list restricts it."""

    op: Literal["establish"] = "establish"
    entity: str
    text: str
    known_by: Optional[list[str]] = None
    ref: Optional[str] = None


class Supersede(_Change):
    """Mark a fact as no longer true. Add a replacement with a separate Establish."""

    op: Literal["supersede"] = "supersede"
    fact: str


class Reveal(_Change):
    """Tell characters (or groups) a restricted fact."""

    op: Literal["reveal"] = "reveal"
    fact: str
    to: list[str]


class Connect(_Change):
    """Add a labelled link between two entities (a door between locations)."""

    op: Literal["connect"] = "connect"
    from_id: str
    to_id: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class Disconnect(_Change):
    op: Literal["disconnect"] = "disconnect"
    from_id: str
    to_id: str
    label: str


class Record(_Change):
    """Log-only event that changes no state (a dice roll, a ruling)."""

    op: Literal["record"] = "record"
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)


Change = Annotated[
    Union[Create, Update, Move, Remove, Establish, Supersede, Reveal, Connect, Disconnect, Record],
    Field(discriminator="op"),
]

_adapter: TypeAdapter[list[Change]] = TypeAdapter(list[Change])


def parse_changes(raw: Sequence[Any]) -> list[Change]:
    """Validate a list of change dicts (for example an LLM proposal) into change models."""
    return _adapter.validate_python(list(raw))
