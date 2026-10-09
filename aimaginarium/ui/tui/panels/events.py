"""Panels that list one kind of trace record as an expandable tree: world diffs and check workings."""

import json

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Tree

from ....api import Envelope, TraceEvent
from . import DevPanel, dev_panel


class EventTree(DevPanel):
    """Lists the trace records of one ``kind`` as tree nodes, each expanding into detail lines."""

    kind = ""
    DEFAULT_CSS = "EventTree Tree { height: 1fr; }"

    def compose(self) -> ComposeResult:
        tree: Tree[None] = Tree(self.title)
        tree.show_root = False
        yield tree

    def label(self, event: TraceEvent) -> str:
        raise NotImplementedError

    def details(self, event: TraceEvent) -> list[str]:
        raise NotImplementedError

    def on_envelope(self, envelope: Envelope) -> None:
        event = envelope.event
        if not isinstance(event, TraceEvent) or event.kind != self.kind:
            return
        tree = self.query_one(Tree)
        node = tree.root.add(Text(f"Turn {event.turn_id}: {self.label(event)}"), expand=True)
        for line in self.details(event):
            node.add_leaf(Text(line))
        tree.scroll_end(animate=False)


@dev_panel
class DiffPanel(EventTree):
    """What each turn changed in the world."""

    title = "Diffs"
    kind = "state.diff"

    def label(self, event: TraceEvent) -> str:
        return ", ".join(e["kind"] for e in event.payload["events"]) or "no change"

    def details(self, event: TraceEvent) -> list[str]:
        return [f"{e['kind']}: {json.dumps(e['payload'], default=str, ensure_ascii=False)}"[:200]
                for e in event.payload["events"]]


@dev_panel
class ChecksPanel(EventTree):
    """How each check's difficulty was reached and what the roll made of it."""

    title = "Checks"
    kind = "check.workings"

    def label(self, event: TraceEvent) -> str:
        p = event.payload
        return (f"{p['skill']} {p['tier']}, difficulty {p['difficulty']}; rolled {p['die']} {p['modifier']:+d} = "
                f"{p['total']} ({p['classification']})")

    def details(self, event: TraceEvent) -> list[str]:
        p = event.payload
        lines = [f"Reason: {p.get('reason', '')}", f"Tier {p['tier']}: base {p.get('base')}"]
        lines += [f"{a['what']}: {a['delta']:+d}" for a in p.get("adjustments", [])]
        lines.append(f"Adjustment applied: {p.get('adjustment', 0):+d}, so difficulty {p['difficulty']}")
        lines.append(f"Roll: {p['die']} {p['modifier']:+d} = {p['total']}: {p['classification']}")
        return lines
