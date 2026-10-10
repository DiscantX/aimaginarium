"""The log pane: Python log records from the engine and providers, filterable by level and component."""

import logging
from collections import deque

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Select

from ..hanging import Blocks, Hanging
from ..views import SelectableText
from . import DevPanel, dev_panel

LEVELS = [("Debug", logging.DEBUG), ("Info", logging.INFO), ("Warning", logging.WARNING), ("Error", logging.ERROR)]
STYLES = {logging.DEBUG: "dim", logging.INFO: "", logging.WARNING: "yellow", logging.ERROR: "bold red"}


class LogRecorded(Message):
    """A log record was written somewhere in the game."""

    def __init__(self, record: logging.LogRecord) -> None:
        super().__init__()
        self.record = record


class TuiLogHandler(logging.Handler):
    """Keeps the latest records and tells the app about each, from whatever thread logged it."""

    def __init__(self, app, keep: int = 2000) -> None:
        super().__init__(logging.DEBUG)
        self.app = app
        self.records: deque[logging.LogRecord] = deque(maxlen=keep)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        try:
            self.app.post_message(LogRecorded(record))
        except Exception:  # the app is shutting down
            pass


@dev_panel
class LogPane(DevPanel):
    """A level selector, a component filter (a substring of the logger name) and the matching records."""

    title = "Log"
    DEFAULT_CSS = """
    LogPane Horizontal { height: auto; }
    LogPane Select { width: 20; }
    LogPane Input { width: 1fr; }
    LogPane SelectableText { height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.shown: list[str] = []
        self._lines: list[Hanging] = []
        self._pending = False

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Select(LEVELS, value=logging.INFO, allow_blank=False, id="level")
            yield Input(placeholder="component (logger name contains)", id="component")
        yield SelectableText()

    @property
    def handler(self) -> TuiLogHandler | None:
        return getattr(self.app, "log_handler", None)

    def on_mount(self) -> None:
        self.redraw()

    def matches(self, record: logging.LogRecord) -> bool:
        level = self.query_one("#level", Select).value
        return record.levelno >= level and self.query_one("#component", Input).value.lower() in record.name.lower()

    def add(self, record: logging.LogRecord) -> None:
        if self.matches(record):
            line = f"{record.created % 86400:>8.2f} {record.levelname:<7} {record.name}: {record.getMessage()}"
            self.shown.append(line)
            del self.shown[:-2000], self._lines[:-2000 + 1]          # the pane keeps what the handler keeps
            self._lines.append(Hanging(Text(line, style=STYLES.get(record.levelno, "")), "", "    "))
            if not self._pending:                     # several records at once are drawn once
                self._pending = True
                self.set_timer(0.05, self._flush)

    def _flush(self) -> None:
        """Draws the lines, staying at the end if the view was at the end."""
        self._pending = False
        view = self.query_one(SelectableText)
        at_end = view.scroll_y >= view.max_scroll_y - 1
        view.show(Blocks(self._lines))
        if at_end:
            view.call_after_refresh(view.scroll_end, animate=False)

    def redraw(self) -> None:
        self.shown.clear()
        self._lines.clear()
        self.query_one(SelectableText).show(None)
        for record in (self.handler.records if self.handler else ()):
            self.add(record)

    @on(Select.Changed)
    @on(Input.Changed)
    def _filter_changed(self) -> None:
        self.redraw()
