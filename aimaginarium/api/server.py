"""The server and session protocols that every client programs against.

These are the contract every client programs against. :class:`~.local.LocalServer`
is the in-process implementation the terminal client uses; the Textual UI, the MCP
servers and the web client will use the same two protocols.

A turn that calls for a check spans two replies: ``send(SubmitAction)`` ends
with ``Done(awaiting_roll=True)``, and ``send(Roll)`` continues it. There is no
other way to resume, so a remote client and an in-process one behave alike.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from .commands import Command
from .events import Envelope
from .roles import Role


@runtime_checkable
class Session(Protocol):
    """One client's connection, fixed to one role.

    Attributes:
        role: The role the session was opened for.
    """

    role: Role

    def send(self, command: Command) -> AsyncIterator[Envelope]:
        """Sends a command and streams its reply, ending with ``Done``.

        Raises:
            RoleError: If the session's role may not send the command.
        """
        ...

    def subscribe(self, since: int = 0) -> AsyncIterator[Envelope]:
        """Streams every envelope the role may see, from sequence ``since`` onward, as it happens."""
        ...

    async def close(self) -> None:
        """Ends the session."""
        ...


@runtime_checkable
class Server(Protocol):
    """Opens sessions."""

    def connect(self, role: Role = Role.PLAYER) -> Session:
        """Opens a session.

        Raises:
            RoleError: If the dev role is requested while config disables it.
        """
        ...
