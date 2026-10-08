"""The Textual app: the story, the action input and the roll modal, on an API session."""

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header

from ...api import GetPlayerView, OpenScene, Quit, Role, Session, StateView, SubmitAction
from ...llm import ConfigError
from .dev import preview_roll
from .inputs import ActionInput, PasteConfirm
from .runner import TurnRunner
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
    ActionInput { margin: 0 1; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    def __init__(self, session: Session, opening: bool = True) -> None:
        super().__init__()
        self.session, self.opening = session, opening
        self.runner: TurnRunner

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(ROLE_DEFAULTS)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="story-column"):
            yield StoryLog(id="story")
            yield Thinking(id="thinking")
            yield ActionInput(placeholder="What do you do?", id="action")
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(CANDLELIT)
        self.theme = CANDLELIT.name
        self.runner = TurnRunner(self, self.session, self.story, self._set_busy)
        self.query_one(ActionInput).focus()
        if self.opening:
            self._start(OpenScene())
        else:
            await self._replay()

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

    async def action_quit(self) -> None:
        async for _ in self.session.send(Quit()):
            pass
        await self.session.close()
        self.exit()
