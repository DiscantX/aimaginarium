"""The party bar: one bordered card per party member, selectable.

Selecting a card changes the *viewed* character (what a character panel shows). It never changes whose
point of view the story has or whom the input is addressed to: that stays the player's own character.
The bar is dock-agnostic: ``orientation`` decides whether it lays out as a row (top) or a column (right).
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.message import Message
from textual.widget import Widget

from ..party import Controller, PartyMember

HP_CELLS = 10
CONTROLLER_TAGS = {Controller.HUMAN: "", Controller.LLM_MCP: "AI·MCP", Controller.LLM_INTERNAL: "AI"}


def hp_bar(member: PartyMember, cells: int = HP_CELLS) -> str:
    """``"14/20 ▓▓▓▓▓▓▓░░░"``, or ``"HP ?"`` when the hit points are not known to the viewer."""
    fraction = member.hp_fraction
    if fraction is None:
        return "HP ?"
    filled = round(fraction * cells)
    if member.hp and filled == 0:
        filled = 1  # alive is never shown as an empty bar
    return f"{member.hp}/{member.max_hp} " + "▓" * filled + "░" * (cells - filled)


def hp_style(member: PartyMember) -> str:
    """Name of the component class colouring the HP line."""
    fraction = member.hp_fraction
    if fraction is None:
        return "partycard--dim"
    return "partycard--hp-high" if fraction > 0.5 else "partycard--hp-mid" if fraction > 0.25 else "partycard--hp-low"


class PartyCard(Widget):
    """One member: class and level, HP bar and status markers inside a border titled with the name.

    The title carries a star for the player's own character and the subtitle names an AI controller.
    ``selected`` (the viewed character) is a CSS class, so a theme can restyle it.
    """

    COMPONENT_CLASSES = {"partycard--dim", "partycard--hp-high", "partycard--hp-mid", "partycard--hp-low"}
    DEFAULT_CSS = """
    PartyCard {
        width: 24; height: 6; padding: 0 1; border: round $secondary; background: $surface;
        border-title-color: $foreground; border-subtitle-color: $system;
    }
    PartyCard:hover { border: round $primary; }
    PartyCard.mine { border-title-color: $primary; }
    PartyCard.selected { border: heavy $accent; background: $panel; }
    PartyCard > .partycard--dim { color: $system; }
    PartyCard > .partycard--hp-high { color: $success; }
    PartyCard > .partycard--hp-mid { color: $warning; }
    PartyCard > .partycard--hp-low { color: $error; }
    """

    class Clicked(Message):
        """The card was clicked."""

        def __init__(self, member_id: str) -> None:
            super().__init__()
            self.member_id = member_id

    def __init__(self, member: PartyMember) -> None:
        super().__init__()
        self.member = member

    def on_mount(self) -> None:
        self.update(self.member)

    def update(self, member: PartyMember) -> None:
        """Shows a new state of the same member."""
        self.member = member
        self.border_title = ("★ " if member.mine else "") + member.name
        self.border_subtitle = CONTROLLER_TAGS[member.controller]
        self.set_class(member.mine, "mine")
        self.refresh()

    def render(self) -> Text:
        m = self.member
        dim = self.get_component_rich_style("partycard--dim")
        text = Text()
        text.append((m.subtitle or "—") + "\n", style=dim)
        text.append(hp_bar(m) + "\n", style=self.get_component_rich_style(hp_style(m)))
        text.append(" · ".join(m.statuses) or "—", style=dim)
        return text

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self.member.id))


class PartyBar(ScrollableContainer, can_focus=True):
    """The party as a scrolling strip of :class:`PartyCard`: a row (``top``) or a column (``right``).

    Keys while it has focus: the arrows along its axis move the selection, ``enter`` keeps it and returns to the
    input, ``escape`` and ``home`` go back to the player's own character.

    Args:
        orientation: ``"top"`` or ``"right"``.
    """

    DEFAULT_CSS = """
    PartyBar { padding: 0 1; }
    PartyBar.-top { layout: horizontal; overflow-x: auto; overflow-y: hidden; height: 7; }
    PartyBar.-right { layout: vertical; overflow-x: hidden; overflow-y: auto; width: 28; height: 1fr; }
    PartyBar:focus { background: $surface 30%; }
    """
    BINDINGS = [
        Binding("left,up", "move(-1)", show=False),
        Binding("right,down", "move(1)", show=False),
        Binding("home,escape", "mine", "My character"),
        Binding("enter", "done", "Done"),
    ]

    class Selected(Message):
        """The viewed character changed."""

        def __init__(self, member: PartyMember) -> None:
            super().__init__()
            self.member = member

    class Done(Message):
        """The player is done with the bar; focus belongs back to the action input."""

    def __init__(self, orientation: str = "top", **kwargs) -> None:
        if orientation not in ("top", "right"):
            raise ValueError(f"unknown party bar placement {orientation!r}; use 'top' or 'right'")
        super().__init__(classes=f"-{orientation}", **kwargs)
        self.orientation = orientation
        self.members: list[PartyMember] = []
        self.selected_id: str | None = None

    @property
    def selected(self) -> PartyMember | None:
        """The member being viewed."""
        return next((m for m in self.members if m.id == self.selected_id), None)

    @property
    def mine(self) -> PartyMember | None:
        """The player's own character."""
        return next((m for m in self.members if m.mine), self.members[0] if self.members else None)

    def cards(self) -> list[PartyCard]:
        return list(self.query(PartyCard))

    async def set_party(self, members: list[PartyMember]) -> None:
        """Shows these members, keeping the selection if that member is still in the party.

        Cards are updated in place when the member list keeps its ids and order; otherwise rebuilt.
        """
        previous_ids = [m.id for m in self.members]
        self.members = list(members)
        if [m.id for m in members] == previous_ids and self.cards():
            for card, member in zip(self.cards(), members):
                card.update(member)
        else:
            await self.remove_children()
            await self.mount(*(PartyCard(m) for m in members))
        if self.selected is None and self.mine is not None:
            self.selected_id = self.mine.id
        self._mark()

    def _mark(self) -> None:
        for card in self.cards():
            card.set_class(card.member.id == self.selected_id, "selected")

    def select(self, member_id: str) -> None:
        """Views this member (a no-op if already viewed or not in the party)."""
        if member_id == self.selected_id or all(m.id != member_id for m in self.members):
            return
        self.selected_id = member_id
        self._mark()
        card = next(c for c in self.cards() if c.member.id == member_id)
        self.scroll_to_widget(card, animate=False)
        self.post_message(self.Selected(card.member))

    WHEEL_STEP = 6
    """Cells a wheel notch scrolls the row, since the wheel is vertical and the top bar scrolls sideways."""

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._wheel(event, 1)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._wheel(event, -1)

    def _wheel(self, event: events.MouseEvent, direction: int) -> None:
        """Turns the vertical wheel into sideways scrolling for the top bar; the column scrolls on its own."""
        if self.orientation == "top":
            event.stop()
            event.prevent_default()
            self.scroll_relative(x=direction * self.WHEEL_STEP, animate=False)

    def on_party_card_clicked(self, event: PartyCard.Clicked) -> None:
        event.stop()
        self.select(event.member_id)

    def action_move(self, step: int) -> None:
        ids = [m.id for m in self.members]
        if ids and self.selected_id in ids:
            self.select(ids[max(0, min(len(ids) - 1, ids.index(self.selected_id) + step))])

    def action_mine(self) -> None:
        if self.mine is not None:
            self.select(self.mine.id)
        self.post_message(self.Done())

    def action_done(self) -> None:
        self.post_message(self.Done())
