"""Views whose text can be selected with the mouse, and the pretty / JSON view of a payload.

Textual can only select text from a widget that shows a ``Text`` or ``Content``; a Rich renderable (a
``Syntax``, a group of blocks) is a picture to it. :class:`SelectableText` therefore lays any renderable out
itself at the pane's width (so hanging indents stay) and shows the lines as ``Content``. What is selected is
exactly what is on screen, and that is what a copy gives.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console, RenderableType
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Static


MODES = ("pretty", "json")
"""The two presentations of a payload: readable blocks, and the exact JSON."""


def layout(renderable: RenderableType | None, width: int) -> Content:
    """The renderable laid out in ``width`` cells, as styled ``Content`` with real line breaks."""
    if renderable is None or width < 1:
        return Content("")
    console = Console(width=width, color_system=None, force_terminal=False, legacy_windows=False)
    lines = console.render_lines(renderable, console.options.update(width=width), pad=False, new_lines=False)
    texts = [Text.assemble(*((segment.text, segment.style) for segment in line if not segment.control))
             for line in lines]
    for text in texts:
        text.rstrip()
    while texts and not texts[-1].plain:
        texts.pop()
    return Content("\n").join(Content.from_rich_text(text) for text in texts)


class SelectableText(VerticalScroll):
    """Scrolls a renderable laid out to its width; the mouse can select the text and copy gives that text."""

    DEFAULT_CSS = """
    SelectableText { height: 1fr; padding: 0 1; scrollbar-gutter: stable; }
    SelectableText > Static { width: 100%; height: auto; }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.renderable: RenderableType | None = None
        self.displayed = ""
        """The text as laid out and shown (wrapped, with its prefixes): what a selection is cut from."""
        self._width = 0

    def compose(self) -> ComposeResult:
        yield Static("", markup=False)

    def show(self, renderable: RenderableType | None) -> None:
        self.renderable = renderable
        self._layout()

    def on_resize(self) -> None:
        self._layout()

    def _layout(self) -> None:
        width = self.scrollable_content_region.width
        if width < 1 or not self.is_mounted:
            return
        self._width = width
        content = layout(self.renderable, width)
        self.displayed = content.plain
        self.query_one(Static).update(content)


class ModeBar(Static):
    """Shows which presentation is active and switches it when a name is clicked."""

    ALLOW_SELECT = False
    """The bar is a control, not content: a selection of the text below must not pick it up."""
    DEFAULT_CSS = "ModeBar { height: 1; padding: 0 1; color: $text-muted; }"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", markup=True, **kwargs)
        self.plain = ""
        """The bar's text without markup."""

    def show(self, mode: str) -> None:
        names = {"pretty": "Pretty", "json": "JSON"}
        self.plain = "View: " + " ".join(f" {names[m]} " for m in MODES) + "   (p switches)"
        parts = [f"[reverse bold] {names[m]} [/]" if m == mode else f"[@click=mode('{m}')] {names[m]} [/]" for m in MODES]
        self.update("View: " + " ".join(parts) + "   (p switches)")

    def action_mode(self, mode: str) -> None:
        self.app.set_payload_mode(mode)  # type: ignore[attr-defined]


class PayloadView(Vertical):
    """A payload (anything JSON-like), shown pretty or as exact JSON, with a bar that says which.

    The mode is the app's (``payload_mode``), so every view in the dock switches together.
    """

    DEFAULT_CSS = "PayloadView { height: 1fr; }"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.value: Any = None
        self.has_value = False

    def compose(self) -> ComposeResult:
        yield ModeBar()
        yield SelectableText()

    @property
    def mode(self) -> str:
        return getattr(self.app, "payload_mode", "pretty")

    @property
    def shown(self) -> str:
        """What is shown, unwrapped: the pretty text or the exact JSON."""
        from .panels.pretty import pretty, raw
        if not self.has_value:
            return ""
        return pretty(self.value).plain if self.mode == "pretty" else raw(self.value)

    @property
    def displayed(self) -> str:
        """What is on screen, wrapped: what the mouse selects from."""
        return self.query_one(SelectableText).displayed

    def on_mount(self) -> None:
        self.refresh_mode()

    def show(self, value: Any) -> None:
        self.value, self.has_value = value, True
        self.refresh_mode()

    def refresh_mode(self) -> None:
        from .panels.pretty import pretty, raw
        self.query_one(ModeBar).show(self.mode)
        if not self.has_value:
            return
        if self.mode == "pretty":
            renderable: RenderableType = pretty(self.value)
        else:
            renderable = Syntax(raw(self.value), "json", word_wrap=True, background_color="default")
        self.query_one(SelectableText).show(renderable)
