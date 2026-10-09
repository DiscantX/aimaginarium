"""The state inspector: the world as the GM sees it, or as the player's projection."""

import json

from rich.syntax import Syntax
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import RadioButton, RadioSet, Static

from ....api import Envelope, GetState, StateChanged, StateView
from . import DevPanel, dev_panel


@dev_panel
class StateInspector(DevPanel):
    """Shows ``GetState`` for the chosen perspective and refreshes whenever the world changes."""

    title = "State"
    raw = ""
    """The text currently shown, without styling."""
    DEFAULT_CSS = """
    StateInspector RadioSet { layout: horizontal; height: auto; border: none; background: transparent; }
    StateInspector VerticalScroll { height: 1fr; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toggle"):
            with RadioSet():
                yield RadioButton("GM", value=True, id="gm")
                yield RadioButton("Player", id="player")
        with VerticalScroll():
            yield Static("", id="view")

    def on_mount(self) -> None:
        self.refresh_view()

    @property
    def perspective(self) -> str:
        return "player" if self.query_one("#player", RadioButton).value else "gm"

    def on_envelope(self, envelope: Envelope) -> None:
        if isinstance(envelope.event, StateChanged):
            self.refresh_view()

    @on(RadioSet.Changed)
    def _toggled(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        self.run_worker(self._load(self.perspective), exclusive=True, group="state")

    async def _load(self, perspective: str) -> None:
        async for envelope in self.app.session.send(GetState(perspective)):
            if isinstance(envelope.event, StateView):
                self.query_one("#view", Static).update(self._content(envelope.event))

    def _content(self, view: StateView):
        if view.perspective == "player":
            self.raw = json.dumps(view.data, indent=2, ensure_ascii=False)
            return Syntax(self.raw, "json", word_wrap=True, background_color="default")
        text = Text()
        for name, body in view.data.items():
            text.append(f"{name}\n", style="bold")
            text.append(f"{body}\n\n")
        self.raw = text.plain
        return text
