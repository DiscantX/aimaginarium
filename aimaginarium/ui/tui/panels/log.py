"""The log pane: Python log records from the engine and providers, filterable by level and component."""

import logging
from collections import deque

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, RichLog, Select

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
    LogPane RichLog { height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.shown: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Select(LEVELS, value=logging.INFO, allow_blank=False, id="level")
            yield Input(placeholder="component (logger name contains)", id="component")
        yield RichLog(markup=False, highlight=False, wrap=True)

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
            self.query_one(RichLog).write(Text(line, style=STYLES.get(record.levelno, "")))

    def redraw(self) -> None:
        self.shown.clear()
        self.query_one(RichLog).clear()
        for record in (self.handler.records if self.handler else ()):
            self.add(record)

    @on(Select.Changed)
    @on(Input.Changed)
    def _filter_changed(self) -> None:
        self.redraw()
