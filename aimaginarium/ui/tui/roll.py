"""The roll modal: shows the check, waits for the player to roll, then tumbles the die and reveals the result."""

import asyncio
import random

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Digits, Static

from ...api import CheckCalled, RollResult

DIE_SIDES = 20

LABELS = {
    "critical_failure": "Critical failure",
    "failure": "Failure",
    "narrow_success": "Narrow success",
    "success": "Success",
    "critical_success": "Critical success",
}


def label(classification: str) -> str:
    """A classification as words for the player."""
    return LABELS.get(classification, classification.replace("_", " ").capitalize())


class Dice(Digits):
    """A big number that tumbles. Its face is a pure function of ``progress``, so an animation can land on any value."""

    progress = reactive(0.0, init=False)

    def __init__(self, sides: int = DIE_SIDES) -> None:
        super().__init__("--")
        self.sides = sides
        self.start = random.randrange(sides)

    def face(self, progress: float) -> int:
        return (self.start + int(progress)) % self.sides + 1

    def watch_progress(self, progress: float) -> None:
        self.update(f"{self.face(progress):2d}")

    def target_for(self, die: int, turns: int) -> float:
        """The progress value, a few full turns ahead, whose face is ``die``."""
        ahead = int(self.progress) + self.sides * turns
        return float(ahead + (die - 1 - self.start - ahead) % self.sides)


class RollScreen(ModalScreen[None]):
    """Presents a called check. The player rolls; the result lands with an animation and then the modal closes.

    The runner drives it: it waits on :attr:`requested`, sends the roll, hands the result to :meth:`land`,
    and waits on :attr:`closed`.
    """

    DEFAULT_CSS = """
    RollScreen { align: center middle; }
    RollScreen > Vertical { width: 44; height: auto; padding: 1 3; background: $panel; border: round $primary; }
    RollScreen > Vertical > * { width: 100%; }
    RollScreen #skill { text-style: bold; color: $primary; width: 100%; text-align: center; }
    RollScreen #difficulty { color: $system; width: 100%; text-align: center; margin-bottom: 1; }
    RollScreen Dice { text-align: center; margin: 1 0; color: $roll; }
    RollScreen Dice.max { color: $success; }
    RollScreen Dice.min { color: $error; }
    RollScreen #breakdown, RollScreen #verdict { width: 100%; text-align: center; opacity: 0; }
    RollScreen #verdict { text-style: bold; margin-bottom: 1; }
    RollScreen #verdict.success { color: $success; }
    RollScreen #verdict.failure { color: $error; }
    RollScreen #roll-row { height: auto; margin-top: 1; }
    """
    BINDINGS = [Binding("r", "roll", "Roll")]

    hold = 1.2
    """Seconds the finished result stays up before the modal closes by itself."""
    tumble = 1.8
    """Seconds the die takes to settle."""

    def __init__(self, check: CheckCalled) -> None:
        super().__init__()
        self.check = check
        self.requested = asyncio.Event()
        self.closed = asyncio.Event()
        self.phase = "ready"
        self.result: RollResult | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.check.skill.title(), id="skill")
            yield Static(f"Difficulty {self.check.difficulty}", id="difficulty")
            yield Dice()
            yield Static("", id="breakdown", markup=False)
            yield Static("", id="verdict")
            with Center(id="roll-row"):
                yield Button("Roll", id="roll", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#roll").focus()

    @on(Button.Pressed, "#roll")
    def action_roll(self) -> None:
        if self.phase != "ready":
            return
        self.phase = "rolling"
        self.query_one("#roll-row").display = False
        self._spin = self.set_interval(0.06, self._spin_once)
        self.requested.set()

    def _spin_once(self) -> None:
        dice = self.query_one(Dice)
        dice.progress += random.randint(1, dice.sides - 1)

    def land(self, result: RollResult) -> None:
        """Settles the die on the real result, then reveals the working and the verdict."""
        if self.phase != "rolling":
            return
        self.phase, self.result = "landing", result
        self._spin.stop()
        dice = self.query_one(Dice)
        dice.animate("progress", dice.target_for(result.die, 3), duration=self.tumble, easing="out_cubic",
                     on_complete=self._reveal)

    def _reveal(self) -> None:
        if self.phase != "landing" or self.result is None:
            return
        self.phase = "shown"
        r = self.result
        dice = self.query_one(Dice)
        dice.progress = dice.target_for(r.die, 0)
        won = r.classification.endswith("success")
        dice.set_class(r.classification == "critical_success", "max")
        dice.set_class(r.classification == "critical_failure", "min")
        self.query_one("#breakdown").update(f"{r.die} {r.modifier:+d} = {r.total}  (needed {r.difficulty})")
        verdict = self.query_one("#verdict")
        verdict.update(label(r.classification))
        verdict.set_class(won, "success")
        verdict.set_class(not won, "failure")
        self.query_one("#breakdown").styles.animate("opacity", 1.0, duration=0.4)
        verdict.styles.animate("opacity", 1.0, duration=0.4, delay=0.4, on_complete=self._start_hold)

    def _start_hold(self) -> None:
        if self.hold > 0:
            self.set_timer(self.hold, self.finish)
        else:
            self.finish()

    async def on_key(self, event) -> None:
        if self.phase == "landing":
            await self.query_one(Dice).stop_animation("progress", complete=True)
            self._reveal()
            event.stop()
        elif self.phase == "shown":
            self.finish()
            event.stop()

    def finish(self) -> None:
        """Closes the modal (idempotent)."""
        if self.phase != "done":
            self.phase = "done"
            self.closed.set()
            self.dismiss(None)

    def abort(self) -> None:
        """Closes the modal when no result is coming (the roll was refused or the reply failed)."""
        self.requested.set()
        self.finish()
