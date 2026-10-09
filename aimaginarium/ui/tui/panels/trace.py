"""The trace timeline: every thing the engine and the models did, with the full payload of the selected row."""

import json
from datetime import datetime

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Static
from textual_widgets import HorizontalSplitter

from ....api import Envelope, TraceEvent
from ....trace import summarize
from . import DevPanel, dev_panel


@dev_panel
class TraceTimeline(DevPanel):
    """A row per trace record (turn, offset, kind, summary); the highlighted row's payload shows underneath."""

    title = "Trace"
    DEFAULT_CSS = """
    TraceTimeline #trace-rows { height: 2fr; }
    TraceTimeline #detail { height: 1fr; padding: 0 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.records: dict[str, TraceEvent] = {}
        self._start: datetime | None = None

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", zebra_stripes=True, id="trace-rows")
        yield HorizontalSplitter(target_id="trace-rows", min_size=4)
        with VerticalScroll(id="detail"):
            yield Static("", id="payload")

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("turn", "offset", "kind", "summary")

    def on_envelope(self, envelope: Envelope) -> None:
        event = envelope.event
        if not isinstance(event, TraceEvent):
            return
        at = datetime.fromisoformat(event.at)
        self._start = self._start or at
        key = str(event.trace_seq)
        self.records[key] = event
        table = self.query_one(DataTable)
        table.add_row("" if event.turn_id is None else str(event.turn_id), f"+{(at - self._start).total_seconds():.2f}s",
                      event.kind, summarize(event.kind, event.payload)[:120], key=key)
        table.scroll_end(animate=False)

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        event = self.records.get(message.row_key.value or "")
        if event is not None:
            body = json.dumps(event.payload, indent=2, default=str, ensure_ascii=False)
            self.query_one("#payload", Static).update(Syntax(body, "json", word_wrap=True, background_color="default"))
