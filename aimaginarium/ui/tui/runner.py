"""Plays turns: sends commands over the API session and renders each reply stream into the story log."""

from typing import Callable, Optional

from textual.app import App

from ...api import (
    ChangesRejected, CheckCalled, CommandRejected, Done, Narration, Repairing, ReplyUnreadable, Roll, RollResult,
    Session,
)
from .roll import RollScreen, label
from .story import StoryLog


def roll_line(result: RollResult) -> str:
    """The roll as one line of the log."""
    return (f"{result.skill.title()}: rolled {result.die} {result.modifier:+d} = {result.total} "
            f"against {result.difficulty}, {label(result.classification).lower()}")


class TurnRunner:
    """Sends a turn command and, whenever a check is called, runs the roll modal and sends the roll.

    Args:
        app: The app that hosts the modals.
        session: The API session.
        story: The log that receives the narration, rolls and notes.
        busy: Called with True while the storyteller is working and False once it speaks.
    """

    def __init__(self, app: App, session: Session, story: StoryLog, busy: Callable[[bool], None]) -> None:
        self.app, self.session, self.story, self.busy = app, session, story, busy

    async def run(self, command) -> None:
        screen: Optional[RollScreen] = None
        while command is not None:
            check, done = await self._reply(command, screen)
            command, screen = None, None
            if done.awaiting_roll and check is not None:
                screen = RollScreen(check)
                await self.app.push_screen(screen)
                await screen.requested.wait()
                command = Roll()

    async def _reply(self, command, screen: Optional[RollScreen]) -> tuple[Optional[CheckCalled], Done]:
        check, done, entry = None, Done(), None
        landed = False
        self.busy(True)

        def note(text: str) -> None:
            self.story.add(text, "system")

        try:
            async for envelope in self.session.send(command):
                event = envelope.event
                if isinstance(event, Narration):
                    self.busy(False)
                    entry = entry or self.story.add("", "narration")
                    entry.append(event.text)
                    self.story.call_after_refresh(self.story.scroll_end, animate=False)
                    continue
                entry = None
                if isinstance(event, CheckCalled):
                    check = event
                elif isinstance(event, RollResult):
                    self.story.add(roll_line(event), "roll")
                    if screen is not None:
                        screen.land(event)
                        landed = True
                elif isinstance(event, Repairing):
                    self.busy(True)
                elif isinstance(event, ChangesRejected):
                    why = f": {event.errors[0]}" if event.errors else ""
                    note(f"[Some changes were not accepted{why}. The world is unchanged.]")
                elif isinstance(event, ReplyUnreadable):
                    note(f"[{event.reason}]")
                elif isinstance(event, CommandRejected):
                    note(f"[{event.message}]")
                elif isinstance(event, Done):
                    done = event
        finally:
            self.busy(False)
            if screen is not None:
                if landed:
                    await screen.closed.wait()
                else:
                    screen.abort()
        return check, done
