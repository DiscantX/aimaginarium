"""The Textual app: the story, the action input and the roll modal, on an API session."""

import logging

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, TabbedContent
from textual_widgets import HorizontalSplitter, VerticalSplitter

from ...api import (
    AddDevNote, CommandRejected, DevNoteAdded, Envelope, GetPlayerView, OpenScene, Quit, Role, Session, StateChanged, StateView, SubmitAction,
    TurnRetracted, Undo,
)
from ...llm import ConfigError
from .. import devnote
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
from .views import PayloadView
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
    #workspace { layout: horizontal; }
    #workspace.dock-bottom { layout: vertical; }
    #dev-dock { width: 1fr; height: 1fr; }
    #workspace.dock-shown.dock-right #main { width: 11fr; }
    #workspace.dock-shown.dock-right #dev-dock { width: 9fr; }
    #workspace.dock-shown.dock-bottom #main { height: 3fr; }
    #workspace.dock-shown.dock-bottom #dev-dock { height: 2fr; }
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
        self.payload_mode = "pretty"
        """How every payload view in the dev dock is shown: ``"pretty"`` or ``"json"``."""
        self._dock_sizes: dict[str, object] = {"right": None, "bottom": None}
        """The dragged size of the play area (``#main``: its width with the dock on the right, its height with the
        dock at the bottom) for each placement, kept while the dock is hidden or placed elsewhere."""
        self._demo_party_size: int | None = None
        self._party_shown: bool | None = None
        """The player's choice to show or hide the party bar; ``None`` leaves it to the party size."""

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(ROLE_DEFAULTS)

    def compose(self) -> ComposeResult:
        yield Header()
        dev = self.session.role is Role.DEV
        party = self.settings.party_placement
        if party == "top":
            yield PartyBar("top", id="party")
        with Container(id="workspace", classes=self._workspace_classes(dev)):
            with Horizontal(id="main"):
                yield CharacterPanel(id="character-panel")
                yield VerticalSplitter(target_id="character-panel", min_size=28, id="character-splitter")
                with Vertical(id="story-column"):
                    yield StoryLog(id="story")
                    yield Thinking(id="thinking")
                    yield ActionInput(placeholder="What do you do?", id="action")
                if party == "right" and not self._dock_on_right:
                    yield PartyBar("right", id="party")
            if dev:
                yield self._dock_splitter()
                with TabbedContent(id="dev-dock"):
                    yield from dock_panes()
            if party == "right" and self._dock_on_right:
                yield PartyBar("right", id="party")
        yield Footer()

    @property
    def _dock_on_right(self) -> bool:
        return self.session.role is Role.DEV and self.settings.dock_placement == "right"

    def _workspace_classes(self, dev: bool) -> str:
        return f"dock-{self.settings.dock_placement} dock-shown" if dev else ""

    def _dock_splitter(self) -> VerticalSplitter | HorizontalSplitter:
        """The dock's splitter: it sizes the play area, sideways beside the dock or up and down above it."""
        if self.settings.dock_placement == "right":
            return VerticalSplitter(target_id="main", min_size=50, id="dock-splitter")
        return HorizontalSplitter(target_id="main", min_size=8, id="dock-splitter")

    async def on_mount(self) -> None:
        self.register_theme(CANDLELIT)
        self.theme = CANDLELIT.name
        self.runner = TurnRunner(self, self.session, self.story, self._set_busy)
        self.query_one(ActionInput).focus()
        if self.session.role is Role.DEV:
            self.sub_title = "dev: /roll, /undo, /dn, /log, /party, /dock, F2 panels"
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
        await self._remount_party()

    async def _remount_party(self) -> None:
        """Puts the party bar where its placement says (and where the dock leaves room), keeping party and selection."""
        placement = self.settings.party_placement
        selected = self.viewed.id if self.viewed else None
        await self.query_one(PartyBar).remove()
        bar = PartyBar(placement, id="party")
        if placement == "top":
            await self.mount(bar, before="#workspace")
        elif self._dock_on_right:
            await self.query_one("#workspace").mount(bar)       # the far right, past the dock
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
        elif text.split()[:1] == ["/dock"] and self.session.role is Role.DEV:
            await self._dock_command(text.split()[1:])
        elif text.split()[:1] and text.split()[0] in devnote.COMMANDS and self.session.role is Role.DEV:
            await self._dev_note_command(text.split(maxsplit=1)[1] if " " in text else "")
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

    async def _dev_note_command(self, args: str) -> None:
        """``/dn [turn] [#tag ...] text`` (or ``/dev-note``): attaches a dev note to a turn (the latest by default)."""
        try:
            parsed = devnote.parse(args)
        except ValueError as exc:
            self.story.add(str(exc), "system")
            return
        async for envelope in self.session.send(AddDevNote(parsed.text, parsed.turn, parsed.tags)):
            event = envelope.event
            if isinstance(event, DevNoteAdded):
                self.story.add(devnote.confirmation(event.note), "system")
            elif isinstance(event, CommandRejected):
                self.story.add(event.message, "system")

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

    def set_payload_mode(self, mode: str) -> None:
        """Switches every payload view (State, Trace, Diffs, Checks) between pretty and JSON together."""
        self.payload_mode = mode
        for view in self.query(PayloadView):
            view.refresh_mode()

    def _remember_dock_size(self) -> None:
        """Puts the play area's dragged size away (and clears it, so the stylesheet sizes it again)."""
        main = self.query_one("#main")
        attr = "width" if self.settings.dock_placement == "right" else "height"
        self._dock_sizes[self.settings.dock_placement] = getattr(main.styles.inline, attr)
        main.styles.width = None
        main.styles.height = None

    def _restore_dock_size(self) -> None:
        placement = self.settings.dock_placement
        size = self._dock_sizes[placement]
        if size is not None:
            setattr(self.query_one("#main").styles, "width" if placement == "right" else "height", size)

    def action_toggle_dock(self) -> None:
        """Shows or hides the dev dock and its own splitter (the character panel's splitter stays).

        Dragging the splitter gives the play area a size in cells, which would leave the space of a hidden dock
        empty; so the dragged size is put away while the dock is hidden (the play area then fills the space by
        its stylesheet rule) and put back when the dock returns.
        """
        if not self.query("#dev-dock"):
            return
        dock, workspace = self.query_one("#dev-dock"), self.query_one("#workspace")
        show = not dock.display
        if not show:
            self._remember_dock_size()
        for part in (dock, self.query_one("#dock-splitter")):
            part.display = show
        workspace.set_class(show, "dock-shown")
        if show:
            self._restore_dock_size()

    async def set_dock_placement(self, placement: str) -> None:
        """Moves the dev dock to the ``right`` or the ``bottom`` (dev role).

        The dock and its panels stay where they are in the widget tree, so the selected tab, the trace and the log
        all survive; only the layout flips and the splitter is swapped for the other direction. Each placement
        remembers the size it was dragged to.
        """
        if placement not in ("right", "bottom"):
            raise ValueError(f"unknown dock placement {placement!r}; use 'right' or 'bottom'")
        if self.session.role is not Role.DEV or placement == self.settings.dock_placement:
            return
        dock, workspace = self.query_one("#dev-dock"), self.query_one("#workspace")
        shown = dock.display
        if shown:
            self._remember_dock_size()
        self.settings.dock_placement = placement
        workspace.set_class(placement == "right", "dock-right")
        workspace.set_class(placement == "bottom", "dock-bottom")
        await self.query_one("#dock-splitter").remove()
        splitter = self._dock_splitter()
        splitter.display = shown
        await workspace.mount(splitter, before="#dev-dock")
        if shown:
            self._restore_dock_size()
        if self.settings.party_placement == "right":
            await self._remount_party()                          # it sits past the dock, or inside the play area

    async def action_move_dock(self) -> None:
        """Moves the dev dock to the other side."""
        await self.set_dock_placement("bottom" if self.settings.dock_placement == "right" else "right")

    async def _dock_command(self, args: list[str]) -> None:
        """``/dock [right|bottom]``: moves the dock (no argument: to the other side)."""
        if not args:
            await self.action_move_dock()
        elif args[0] in ("right", "bottom"):
            await self.set_dock_placement(args[0])
        else:
            self.story.add("Usage: /dock [right|bottom]", "system")

    async def action_quit(self) -> None:
        async for _ in self.session.send(Quit()):
            pass
        await self.session.close()
        self.exit()
