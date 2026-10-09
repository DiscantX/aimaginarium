"""Dev panels: views for the dev role that sit in the dock beside the story.

A panel is a self-contained view over the API session. It is registered with :func:`dev_panel`, receives
every envelope the session streams through :meth:`DevPanel.on_envelope`, and may query the session itself.
Only the dev role mounts them, so a player session has no panel that could show hidden state.
"""

from textual.binding import Binding
from textual.containers import Vertical

from ....api import Envelope


class DevPanel(Vertical):
    """Base of the dev panels. Subclasses set ``title`` and override :meth:`on_envelope`.

    A panel that has something to copy returns its exact text from :meth:`copy_text`; ``c`` copies it.
    """

    title = "Panel"
    BINDINGS = [Binding("c", "copy", "Copy raw")]

    def copy_text(self) -> str:
        """The exact text ``c`` copies (empty if there is nothing selected)."""
        return ""

    def action_copy(self) -> None:
        text = self.copy_text()
        if text:
            self.app.copy_to_clipboard(text)
            self.app.notify(f"Copied {len(text):,} characters (raw JSON)")

    def on_envelope(self, envelope: Envelope) -> None:
        """Called with every envelope the session streams, in order."""


PANELS: list[type[DevPanel]] = []


def dev_panel(cls: type[DevPanel]) -> type[DevPanel]:
    """Registers a panel class to be mounted in the dev dock."""
    PANELS.append(cls)
    return cls


from . import trace, state, events, log  # noqa: E402,F401  (importing registers the panels)

__all__ = ["DevPanel", "PANELS", "dev_panel"]
