"""Panels that list one kind of trace record as a tree of one-line entries, with the full entry underneath.

Each line is cut to the panel's width so nothing scrolls sideways; select a line to read all of it.
"""

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual_widgets import HorizontalSplitter

from ....api import Envelope, TraceEvent
from . import DevPanel, dev_panel
from ..views import PayloadView
from .pretty import raw


def fit(line: str, width: int) -> str:
    """Cuts a one-line label to ``width`` characters, ending in an ellipsis."""
    line = " ".join(line.split())
    return line if len(line) <= width else line[: max(width - 1, 1)] + "…"


class EventTree(DevPanel):
    """Lists the trace records of one ``kind`` as tree nodes, each expanding into detail lines.

    A node's ``data`` is the full thing it stands for (the record's payload, or one entry of it), shown pretty in
    the pane below when the node is highlighted.
    """

    kind = ""
    DEFAULT_CSS = """
    EventTree Tree { height: 2fr; }
    EventTree #detail { height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selected: Any = None
        self._labels: dict[int, tuple[TreeNode, str]] = {}

    def compose(self) -> ComposeResult:
        tree: Tree[Any] = Tree(self.title, id="events")
        tree.show_root = False
        yield tree
        yield HorizontalSplitter(target_id="events", min_size=4)
        yield PayloadView(id="detail")

    def label(self, event: TraceEvent) -> str:
        raise NotImplementedError

    def details(self, event: TraceEvent) -> list[tuple[str, Any]]:
        """The expanded lines of a record, each as (line, the full thing it stands for)."""
        raise NotImplementedError

    def on_envelope(self, envelope: Envelope) -> None:
        event = envelope.event
        if not isinstance(event, TraceEvent) or event.kind != self.kind:
            return
        tree = self.query_one(Tree)
        node = tree.root.add(self._cut(f"Turn {event.turn_id}: {self.label(event)}", 0), data=event.payload, expand=True)
        self._labels[node.id] = (node, f"Turn {event.turn_id}: {self.label(event)}")
        for line, full in self.details(event):
            leaf = node.add_leaf(self._cut(line, 1), data=full)
            self._labels[leaf.id] = (leaf, line)
        tree.scroll_end(animate=False)

    def _cut(self, line: str, depth: int) -> Text:
        return Text(fit(line, max(self.query_one(Tree).size.width - 6 - 2 * depth, 20)), no_wrap=True)

    def on_resize(self) -> None:
        """Re-cuts every line to the new width."""
        for node, line in self._labels.values():
            node.set_label(self._cut(line, 0 if node.parent is node.tree.root else 1))

    def on_tree_node_highlighted(self, message: Tree.NodeHighlighted) -> None:
        self.selected = message.node.data
        self._show()

    @property
    def shown(self) -> str:
        """The selected entry as shown, unwrapped (pretty text or exact JSON, by the current mode)."""
        return self.query_one(PayloadView).shown

    def _show(self) -> None:
        if self.selected is not None:
            self.query_one(PayloadView).show(self.selected)

    def copy_text(self) -> str:
        return raw(self.selected) if self.selected is not None else ""


@dev_panel
class DiffPanel(EventTree):
    """What each turn changed in the world."""

    title = "Diffs"
    kind = "state.diff"

    def label(self, event: TraceEvent) -> str:
        return ", ".join(e["kind"] for e in event.payload["events"]) or "no change"

    def details(self, event: TraceEvent) -> list[tuple[str, Any]]:
        import json
        return [(f"{e['kind']}: {json.dumps(e['payload'], default=str, ensure_ascii=False)}", e)
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

    def details(self, event: TraceEvent) -> list[tuple[str, Any]]:
        p = event.payload
        lines = [f"Reason: {p.get('reason', '')}", f"Tier {p['tier']}: base {p.get('base')}"]
        lines += [f"{a['what']}: {a['delta']:+d}" for a in p.get("adjustments", [])]
        lines.append(f"Adjustment applied: {p.get('adjustment', 0):+d}, so difficulty {p['difficulty']}")
        lines.append(f"Roll: {p['die']} {p['modifier']:+d} = {p['total']}: {p['classification']}")
        return [(line, line) for line in lines]
