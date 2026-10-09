"""The Textual app: the story, the action input and the roll modal, on an API session."""

import logging

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, TabbedContent
from textual_widgets import VerticalSplitter

from ...api import (
    CommandRejected, Envelope, GetPlayerView, OpenScene, Quit, Role, Session, StateView, SubmitAction, TurnRetracted,
    Undo,
)
from ...llm import ConfigError
from .commands import DevCommands
from .dev import preview_roll
from .dock import dock_panes
from .inputs import ActionInput, PasteConfirm
from .panels import DevPanel
from .panels.log import LogPane, LogRecorded, TuiLogHandler
from .runner import TurnRunner
from .settings import Settings
from .story import StoryLog
from .thinking import Thinking
from .theme import CANDLELIT, ROLE_DEFAULTS


class GameApp(App):
    """Plays one game through an API session.

    Args:
        session: The session to play through.
        opening: Whether to narrate the opening scene (a game that has not begun) or replay the story so far.
    """

    TITLE = "AImaginarium"
    CSS = """
    #story-column { width: 1fr; }
    #story-column.with-dock { width: 55%; }
    #dev-dock { width: 1fr; }
    ActionInput { margin: 0 1; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True), Binding("f2", "toggle_dock", "Dev panels")]
    COMMANDS = App.COMMANDS | {DevCommands}

    def __init__(self, session: Session, opening: bool = True) -> None:
        super().__init__()
        self.session, self.opening = session, opening
        self.settings = Settings()
        self.runner: TurnRunner
        self.log_handler: TuiLogHandler | None = None

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(ROLE_DEFAULTS)

    def compose(self) -> ComposeResult:
        yield Header()
        dev = self.session.role is Role.DEV
        with Horizontal(id="main"):
            with Vertical(id="story-column", classes="with-dock" if dev else ""):
                yield StoryLog(id="story")
                yield Thinking(id="thinking")
                yield ActionInput(placeholder="What do you do?", id="action")
            if dev:
                yield VerticalSplitter(target_id="story-column", min_size=40)
                with TabbedContent(id="dev-dock"):
                    yield from dock_panes()
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(CANDLELIT)
        self.theme = CANDLELIT.name
        self.runner = TurnRunner(self, self.session, self.story, self._set_busy)
        self.query_one(ActionInput).focus()
        if self.session.role is Role.DEV:
            self.sub_title = "dev: /roll, /undo, F2 panels"
            self.log_handler = TuiLogHandler(self)
            logger = logging.getLogger("aimaginarium")
            logger.addHandler(self.log_handler)
            logger.setLevel(logging.DEBUG)
        self.run_worker(self._follow(), group="follow")
        if self.opening:
            self._start(OpenScene())
        else:
            await self._replay()

    def on_unmount(self) -> None:
        if self.log_handler is not None:
            logging.getLogger("aimaginarium").removeHandler(self.log_handler)

    async def _follow(self) -> None:
        """Passes every envelope the session streams on to the story and the dev panels."""
        async for envelope in self.session.subscribe():
            self._dispatch(envelope)

    def _dispatch(self, envelope: Envelope) -> None:
        if isinstance(envelope.event, TurnRetracted):
            self.story.retract(envelope.event.turn_id, remove=self.session.role is not Role.DEV)
        for panel in self.query(DevPanel):
            panel.on_envelope(envelope)

    @on(LogRecorded)
    def _log_recorded(self, event: LogRecorded) -> None:
        for pane in self.query(LogPane):
            pane.add(event.record)

    @property
    def story(self) -> StoryLog:
        return self.query_one(StoryLog)

    def _set_busy(self, busy: bool) -> None:
        thinking = self.query_one(Thinking)
        thinking.start() if busy else thinking.stop()

    async def _replay(self) -> None:
        """Shows the story so far, for a game that was already begun."""
        async for envelope in self.session.send(GetPlayerView()):
            if isinstance(envelope.event, StateView):
                for part in envelope.event.data["story"]:
                    player = part["speaker"] == "player"
                    self.story.add(("> " if player else "") + part["text"].strip(), "player" if player else "narration")

    def _start(self, command) -> None:
        """Runs a turn in the background, with the input locked until it is over."""
        action = self.query_one(ActionInput)
        action.disabled = True

        async def turn() -> None:
            try:
                await self.runner.run(command)
            except ConfigError as exc:
                self.exit(return_code=2, message=f"configuration problem: {exc}")
            finally:
                action.disabled = False
                action.focus()

        self.run_worker(turn(), exclusive=True)

    @on(ActionInput.Submitted)
    async def _submitted(self, event: ActionInput.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if text in ("/quit", "/exit"):
            await self.action_quit()
        elif text.split()[:1] == ["/roll"] and self.session.role is Role.DEV:
            self.run_worker(preview_roll(self, self.story, text.split()[1:]))
        elif text == "/undo" and self.session.role is Role.DEV:
            await self.action_undo()
        elif text.startswith("/"):
            self.story.add(f"Unknown command {text.split()[0]}.", "system")
        elif text:
            self.story.add(f"> {text}", "player")
            self._start(SubmitAction(text))

    @on(ActionInput.LargePaste)
    def _large_paste(self, event: ActionInput.LargePaste) -> None:
        def decided(accepted: bool | None) -> None:
            if accepted:
                self.query_one(ActionInput).insert_pasted(event.text)

        self.push_screen(PasteConfirm(event.text), decided)

    async def action_undo(self) -> None:
        """Takes back the latest turn (dev role). The story and panels update from the retraction event."""
        if self.session.role is not Role.DEV:
            return
        async for envelope in self.session.send(Undo()):
            if isinstance(envelope.event, CommandRejected):
                self.notify(envelope.event.message, severity="warning")

    def action_preview_roll(self) -> None:
        if self.session.role is Role.DEV:
            self.run_worker(preview_roll(self, self.story, []))

    def action_toggle_dock(self) -> None:
        for dock in self.query("#dev-dock, VerticalSplitter"):
            dock.display = not dock.display
        self.query_one("#story-column").set_class(bool(self.query("#dev-dock")) and self.query_one("#dev-dock").display,
                                                  "with-dock")

    async def action_quit(self) -> None:
        async for _ in self.session.send(Quit()):
            pass
        await self.session.close()
        self.exit()
