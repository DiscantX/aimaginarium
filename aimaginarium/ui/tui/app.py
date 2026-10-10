"""The Textual app: the story, the action input and the roll modal, on an API session."""

import logging

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, TabbedContent
from textual_widgets import VerticalSplitter

from ...api import (
    CommandRejected, Envelope, GetPlayerView, OpenScene, Quit, Role, Session, StateChanged, StateView, SubmitAction,
    TurnRetracted, Undo,
)
from ...llm import ConfigError
from ..character import CharacterView, character_from_member, characters_from_view, demo_character
from ..party import PartyMember, demo_party, party_from_view
from .commands import DevCommands, PlayerCommands
from .dev import preview_roll
from .dock import dock_panes
from .inputs import ActionInput, PasteConfirm
from .panels import DevPanel
from .panels.log import LogPane, LogRecorded, TuiLogHandler
from .character import CharacterPanel
from .party import PartyBar
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
    #story-column.with-dock { width: 11fr; }
    #dev-dock { width: 9fr; }
    ActionInput { margin: 0 1; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f2", "toggle_dock", "Dev panels"),
        Binding("f3", "toggle_party", "Party bar"),
        Binding("f5", "toggle_character", "Character"),
        Binding("f4", "focus_party", "Select party member", show=False),
    ]
    COMMANDS = App.COMMANDS | {DevCommands, PlayerCommands}

    def __init__(self, session: Session, opening: bool = True) -> None:
        super().__init__()
        self.session, self.opening = session, opening
        self.settings = Settings()
        self.runner: TurnRunner
        self.log_handler: TuiLogHandler | None = None
        self.party: list[PartyMember] = []
        self.characters: dict[str, CharacterView] = {}
        self.viewed: PartyMember | None = None
        """The party member being viewed (what a character panel shows); input still goes to the player's own."""
        self._demo_party_size: int | None = None
        self._party_shown: bool | None = None
        """The player's choice to show or hide the party bar; ``None`` leaves it to the party size."""

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(ROLE_DEFAULTS)

    def compose(self) -> ComposeResult:
        yield Header()
        dev = self.session.role is Role.DEV
        if self.settings.party_placement == "top":
            yield PartyBar("top", id="party")
        with Horizontal(id="main"):
            yield CharacterPanel(id="character-panel")
            yield VerticalSplitter(target_id="character-panel", min_size=28, id="character-splitter")
            with Vertical(id="story-column", classes="with-dock" if dev else ""):
                yield StoryLog(id="story")
                yield Thinking(id="thinking")
                yield ActionInput(placeholder="What do you do?", id="action")
            if dev:
                yield VerticalSplitter(target_id="story-column", min_size=40)
                with TabbedContent(id="dev-dock"):
                    yield from dock_panes()
            if self.settings.party_placement != "top":
                yield PartyBar(self.settings.party_placement, id="party")
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(CANDLELIT)
        self.theme = CANDLELIT.name
        self.runner = TurnRunner(self, self.session, self.story, self._set_busy)
        self.query_one(ActionInput).focus()
        if self.session.role is Role.DEV:
            self.sub_title = "dev: /roll, /undo, /log, /party, F2 panels"
            self._watch_logs()
        self.run_worker(self._follow(), group="follow")
        await self._load_party()
        if self.opening:
            self._start(OpenScene())
        else:
            await self._replay()

    def _watch_logs(self) -> None:
        """Feeds every Python log record (ours and the libraries', e.g. httpx) to the Log tab, dev role only."""
        root = logging.getLogger()
        self._root_level = root.level
        self.log_handler = TuiLogHandler(self)
        root.addHandler(self.log_handler)
        root.setLevel(min(root.level or logging.INFO, logging.INFO) if root.level else logging.INFO)
        logging.getLogger("aimaginarium").setLevel(logging.DEBUG)

    def on_unmount(self) -> None:
        if self.log_handler is not None:
            root = logging.getLogger()
            root.removeHandler(self.log_handler)
            root.setLevel(self._root_level)

    async def _follow(self) -> None:
        """Passes every envelope the session streams on to the story and the dev panels."""
        async for envelope in self.session.subscribe():
            self._dispatch(envelope)

    def _dispatch(self, envelope: Envelope) -> None:
        if isinstance(envelope.event, TurnRetracted):
            self.story.retract(envelope.event.turn_id, remove=self.session.role is not Role.DEV)
        if isinstance(envelope.event, StateChanged):
            self.run_worker(self._load_party(), group="party", exclusive=True)
        for panel in self.query(DevPanel):
            panel.on_envelope(envelope)

    async def _load_party(self) -> None:
        """Asks for the player view and shows the party it describes (a stand-in party in dev, if one was asked for)."""
        members: list[PartyMember] = []
        characters: dict[str, CharacterView] = {}
        async for envelope in self.session.send(GetPlayerView()):
            if isinstance(envelope.event, StateView):
                members = party_from_view(envelope.event.data)
                characters = characters_from_view(envelope.event.data, members)
        if self._demo_party_size is not None and members:
            members = demo_party(members[0], self._demo_party_size)
            characters.update({m.id: demo_character(m) for m in members[1:]})
        self.characters = characters
        await self._show_party(members)

    async def _show_party(self, members: list[PartyMember]) -> None:
        """Puts the party on the bar, hiding the bar for a party of one unless the setting says to show it."""
        self.party = members
        bar = self.query_one(PartyBar)
        await bar.set_party(members)
        self._apply_party_visibility()
        self.viewed = bar.selected
        self._show_character()

    def _show_character(self) -> None:
        """Shows the viewed party member's character on the panel."""
        member = self.viewed
        view = None if member is None else self.characters.get(member.id) or character_from_member(member)
        self.query_one(CharacterPanel).show(view)

    def _apply_party_visibility(self) -> None:
        """Shows the bar by the player's choice, or else when the party is more than the player alone."""
        automatic = len(self.party) > 1 or self.settings.party_always_show
        self.query_one(PartyBar).display = automatic if self._party_shown is None else self._party_shown

    async def set_party_placement(self, placement: str) -> None:
        """Moves the party bar to ``top`` or ``right``, keeping the party and the selection."""
        if placement == self.settings.party_placement:
            return
        self.settings.party_placement = placement
        selected = self.viewed.id if self.viewed else None
        await self.query_one(PartyBar).remove()
        bar = PartyBar(placement, id="party")
        if placement == "top":
            await self.mount(bar, before="#main")
        else:
            await self.query_one("#main").mount(bar)
        await bar.set_party(self.party)
        if selected:
            bar.select(selected)
        self._apply_party_visibility()

    @on(PartyBar.Selected)
    def _party_selected(self, event: PartyBar.Selected) -> None:
        """The viewed character changed. Only a view: the story and the input stay with the player's own character."""
        self.viewed = event.member
        self._show_character()

    @on(PartyBar.Done)
    def _party_done(self) -> None:
        self.query_one(ActionInput).focus()

    def action_toggle_party(self) -> None:
        """Shows or hides the party bar (overriding the automatic choice). Showing it also focuses it."""
        bar = self.query_one(PartyBar)
        self._party_shown = not bar.display
        self._apply_party_visibility()
        if bar.display:
            bar.focus()
        else:
            self.query_one(ActionInput).focus()

    def action_toggle_character(self) -> None:
        """Shows or hides the character panel."""
        for widget in self.query("#character-panel, #character-splitter"):
            widget.display = not widget.display

    def action_focus_party(self) -> None:
        """Moves the keyboard to the party bar, if it is shown."""
        bar = self.query_one(PartyBar)
        if bar.display:
            bar.focus()

    async def action_move_party(self) -> None:
        """Moves the party bar to the other side."""
        await self.set_party_placement("right" if self.settings.party_placement == "top" else "top")

    def set_demo_party(self, size: int | None) -> None:
        """Dev: shows ``size`` stand-in members (any number of 1 or more) on the party bar, or the real party for ``None``."""
        if self.session.role is not Role.DEV:
            return
        self._demo_party_size = size
        self.run_worker(self._load_party(), group="party", exclusive=True)

    def action_toggle_demo_party(self) -> None:
        self.set_demo_party(None if self._demo_party_size else 4)

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
        elif text.split()[:1] == ["/party"] and self.session.role is Role.DEV:
            await self._party_command(text.split()[1:])
        elif text == "/undo" and self.session.role is Role.DEV:
            await self.action_undo()
        elif text.split()[:1] == ["/log"] and self.session.role is Role.DEV:
            self._log_test(text.split()[1:])
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

    async def _party_command(self, args: list[str]) -> None:
        """``/party [n|off|top|right]``: n stand-in members (any number, default 4), the real party, or the placement."""
        if args[:1] == ["off"]:
            self.set_demo_party(None)
        elif args[:1] in (["top"], ["right"]):
            await self.set_party_placement(args[0])
        elif not args or args[0].isdigit():
            self.set_demo_party(max(1, int(args[0])) if args else 4)
        else:
            self.story.add("Usage: /party [number|off|top|right]", "system")

    def _log_test(self, args: list[str]) -> None:
        """``/log [debug|info|warning|error] message``: writes a test record, to check the Log tab."""
        level = args[0].upper() if args and args[0].upper() in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"
        words = args[1:] if args and args[0].upper() == level else args
        logging.getLogger("aimaginarium.tui").log(getattr(logging, level), " ".join(words) or "test message")

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
