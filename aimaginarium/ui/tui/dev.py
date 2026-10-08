"""Dev-only tools. They change nothing in the game: they only exercise the UI."""

import asyncio
import random

from textual.app import App

from ...api import CheckCalled, RollResult
from ...engine.rules import DEFAULT_NARROW, classify
from .roll import RollScreen
from .runner import roll_line
from .story import StoryLog


async def preview_roll(app: App, story: StoryLog, args: list[str]) -> None:
    """Runs the roll modal on a made-up check: ``/roll [skill] [difficulty] [die]``.

    No command is sent to the server, so nothing in the world changes. The log line is marked ``[preview]``.
    """
    try:
        skill = args[0] if args else "stealth"
        difficulty = int(args[1]) if len(args) > 1 else 12
        die = int(args[2]) if len(args) > 2 else random.randint(1, 20)
        if not 1 <= die <= 20:
            raise ValueError
    except ValueError:
        story.add("Usage: /roll [skill] [difficulty] [die 1-20]", "system")
        return
    screen = RollScreen(CheckCalled(skill, difficulty), app.settings)
    await app.push_screen(screen)
    await screen.requested.wait()
    await asyncio.sleep(0.8)  # stands in for the storyteller's delay
    modifier = random.randint(0, 4)
    total = die + modifier
    result = RollResult(skill, die, modifier, total, difficulty, classify(die, total - difficulty, DEFAULT_NARROW))
    story.add(f"[preview] {roll_line(result)}", "roll")
    screen.land(result)
    await screen.closed.wait()
