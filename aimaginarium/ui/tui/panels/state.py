"""The state inspector: the world as the GM sees it, or as the player's projection."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import RadioButton, RadioSet

from ....api import Envelope, GetState, StateChanged, StateView
from ..views import PayloadView
from . import DevPanel, dev_panel
from .pretty import raw


@dev_panel
class StateInspector(DevPanel):
    """Shows ``GetState`` for the chosen perspective and refreshes whenever the world changes."""

    title = "State"
    DEFAULT_CSS = """
    StateInspector .toggle { height: auto; }
    StateInspector RadioSet { layout: horizontal; width: auto; height: auto; background: transparent;
                              border: tall transparent; }
    StateInspector RadioSet:focus { border: tall $border; }
    StateInspector PayloadView { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toggle"):
            with RadioSet():
                yield RadioButton("GM", value=True, id="gm")
                yield RadioButton("Player", id="player")
        yield PayloadView(id="view")

    def on_mount(self) -> None:
        self.refresh_view()

    @property
    def raw(self) -> str:
        """The state as shown, unwrapped (pretty text or exact JSON, by the current mode)."""
        return self.query_one(PayloadView).shown

    def copy_text(self) -> str:
        view = self.query_one(PayloadView)
        return raw(view.value) if view.has_value else ""

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
                self.query_one(PayloadView).show(envelope.event.data)
