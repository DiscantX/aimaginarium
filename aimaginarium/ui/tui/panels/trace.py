"""The trace timeline: every thing the engine and the models did, with the full payload of the selected row."""

from datetime import datetime

from textual.app import ComposeResult
from textual.widgets import DataTable
from textual_widgets import HorizontalSplitter

from ....api import Envelope, TraceEvent
from ....trace import summarize
from . import DevPanel, dev_panel
from ..views import PayloadView
from .pretty import raw


@dev_panel
class TraceTimeline(DevPanel):
    """A row per trace record (turn, offset, kind, summary); the highlighted row's payload shows underneath.

    The payload is shown *pretty* by default (multi-line strings as blocks, each real newline marked ``↵``)
    or as the exact JSON (newlines as ``\\n``); ``p`` switches (a bar says which), ``c`` copies the raw JSON, and
    the mouse selects and copies exactly the text shown.
    """

    title = "Trace"
    DEFAULT_CSS = """
    TraceTimeline #trace-rows { height: 2fr; }
    TraceTimeline #detail { height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.records: dict[str, TraceEvent] = {}
        self.selected: TraceEvent | None = None
        self._start: datetime | None = None

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", zebra_stripes=True, id="trace-rows")
        yield HorizontalSplitter(target_id="trace-rows", min_size=4)
        yield PayloadView(id="detail")

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
        self.selected = self.records.get(message.row_key.value or "")
        self._show()

    @property
    def shown(self) -> str:
        """The selected payload as shown, unwrapped (pretty text or exact JSON, by the current mode)."""
        return self.query_one(PayloadView).shown

    def _show(self) -> None:
        if self.selected is not None:
            self.query_one(PayloadView).show(self.selected.payload)

    def copy_text(self) -> str:
        return raw(self.selected.payload) if self.selected else ""
