"""The story log: narration, the player's lines, rolls and system notes, in order."""

from textual.containers import VerticalScroll
from textual.widgets import Static


class Entry(Static):
    """One block of the story. Its ``kind`` (``narration``, ``player``, ``roll``, ``system``) styles it."""

    DEFAULT_CSS = """
    Entry { height: auto; margin: 0 2 1 2; }
    Entry.narration { color: $narration; }
    Entry.player { color: $player; text-style: bold; }
    Entry.roll { color: $roll; border-left: thick $roll; padding-left: 1; }
    Entry.system { color: $system; text-style: italic; }
    Entry.retracted { opacity: 0.4; }
    """

    def __init__(self, text: str, kind: str) -> None:
        super().__init__(text, markup=False, classes=kind)
        self.text = text
        self.kind = kind

    def append(self, more: str) -> None:
        """Adds streamed text to the end of the entry."""
        self.text += more
        self.update(self.text)


class StoryLog(VerticalScroll):
    """Scrolls with the story, staying at the bottom as it grows."""

    DEFAULT_CSS = "StoryLog { height: 1fr; padding-top: 1; }"

    def on_mount(self) -> None:
        self.anchor()

    def add(self, text: str, kind: str = "narration") -> Entry:
        """Appends an entry and returns it, so streamed text can be added to it."""
        entry = Entry(text, kind)
        self.mount(entry)
        self.call_after_refresh(self.scroll_end, animate=False)
        return entry

    def entries(self, kind: str | None = None) -> list[Entry]:
        """The entries so far, optionally only those of one kind."""
        return [e for e in self.query(Entry) if kind is None or e.kind == kind]
