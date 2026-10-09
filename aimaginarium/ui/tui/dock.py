"""The dev dock: one tab per registered dev panel, beside the story."""

from textual.app import ComposeResult
from textual.widgets import TabPane

from .panels import PANELS


def dock_panes() -> ComposeResult:
    """Yields a tab pane holding each dev panel (use inside a ``TabbedContent``)."""
    for cls in PANELS:
        with TabPane(cls.title, id=f"tab-{cls.__name__.lower()}"):
            yield cls()
