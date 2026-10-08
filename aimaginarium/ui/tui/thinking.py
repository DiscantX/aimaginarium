"""The thinking line: a spinner and a playful message while the storyteller works."""

import random

from textual.widgets import Static

from ..waiting import SPIN_FRAMES, WAITING_MESSAGES


class Thinking(Static):
    """A one-line spinner, hidden until :meth:`start` and hidden again by :meth:`stop`."""

    DEFAULT_CSS = """
    Thinking { height: 1; margin: 0 2; display: none; color: $system; }
    Thinking.busy { display: block; }
    """
    interval = 0.08

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._frame = 0
        self._message = ""

    def on_mount(self) -> None:
        self._timer = self.set_interval(self.interval, self._tick, pause=True)

    @property
    def running(self) -> bool:
        return self.has_class("busy")

    def start(self) -> None:
        """Shows the spinner. Called again while already showing, it carries on with the same message."""
        if self.running:
            return
        self._message = random.choice(WAITING_MESSAGES)
        self._tick()
        self.add_class("busy")
        self._timer.resume()

    def stop(self) -> None:
        """Hides the spinner."""
        self._timer.pause()
        self.remove_class("busy")

    def _tick(self) -> None:
        self._frame += 1
        self.update(f"[$accent]{SPIN_FRAMES[self._frame % len(SPIN_FRAMES)]}[/] {self._message}")
