"""The action input, which asks before accepting a large or multi-line paste."""

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

PASTE_LIMIT = 300


class ActionInput(Input):
    """A one-line input. A paste of several lines or more than ``PASTE_LIMIT`` characters is held back."""

    class LargePaste(Message):
        """The player pasted a lot of text; nothing was inserted yet."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def _on_paste(self, event: events.Paste) -> None:
        if "\n" in event.text or len(event.text) > PASTE_LIMIT:
            event.stop()
            event.prevent_default()  # keeps Input's own paste handler from inserting it as well
            self.post_message(self.LargePaste(event.text))

    def insert_pasted(self, text: str) -> None:
        """Inserts confirmed pasted text, with line breaks turned into spaces."""
        self.insert_text_at_cursor(" ".join(text.split()))


class PasteConfirm(ModalScreen[bool]):
    """Asks whether a large paste should really go into the input."""

    DEFAULT_CSS = """
    PasteConfirm { align: center middle; }
    PasteConfirm > Vertical { width: 64; height: auto; padding: 1 2; background: $panel; border: round $primary; }
    PasteConfirm #preview { color: $system; margin: 1 0; max-height: 8; }
    PasteConfirm Horizontal { height: auto; align-horizontal: right; }
    PasteConfirm Button { margin-left: 1; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, text: str) -> None:
        super().__init__()
        self.pasted = text

    def compose(self) -> ComposeResult:
        shown = self.pasted if len(self.pasted) <= 240 else self.pasted[:240] + "…"
        with Vertical():
            yield Static(f"Paste {len(self.pasted)} characters into your action?")
            yield Static(shown, id="preview", markup=False)
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button("Paste", id="paste", variant="primary")

    @on(Button.Pressed, "#paste")
    def _paste(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(False)
