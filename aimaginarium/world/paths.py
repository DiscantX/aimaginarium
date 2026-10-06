"""Dotted-path access into an entity's JSON data (``sheet.hp.current``)."""

from __future__ import annotations

from typing import Any

from .models import Rejected

RESERVED_ROOT = "established"


class PathBlocked(Exception):
    """A path runs through a value that is not an object."""


def split(path: str) -> list[str]:
    segments = path.split(".")
    if not path or any(not s for s in segments):
        raise Rejected("invalid_path", f"invalid path {path!r}")
    if segments[0] == RESERVED_ROOT:
        raise Rejected("reserved_path", "facts are not edited through data; use an establish change")
    return segments


def get(data: dict[str, Any], segments: list[str]) -> tuple[bool, Any]:
    current: Any = data
    for segment in segments:
        if not isinstance(current, dict) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def set_value(data: dict[str, Any], segments: list[str], value: Any) -> None:
    current = data
    for segment in segments[:-1]:
        nxt = current.get(segment)
        if nxt is None:
            nxt = {}
            current[segment] = nxt
        elif not isinstance(nxt, dict):
            raise PathBlocked(segment)
        current = nxt
    current[segments[-1]] = value


def unset_value(data: dict[str, Any], segments: list[str]) -> None:
    found, _ = get(data, segments)
    if not found:
        raise KeyError(".".join(segments))
    _, parent = get(data, segments[:-1]) if len(segments) > 1 else (True, data)
    del parent[segments[-1]]
