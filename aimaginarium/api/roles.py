"""Who is talking to the API.

One API serves two roles. The player role sees projections only (tenet 4); the
dev role also sees the GM's view and the trace. The server refuses the dev role
when config disables it, and enforces both roles itself: hiding tools in a
client is a convenience, not the guard.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """The kinds of client a session can be opened for."""

    PLAYER = "player"
    DEV = "dev"


class RoleError(PermissionError):
    """A role asked for something it may not have, or a disabled role was requested."""
