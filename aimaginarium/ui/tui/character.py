"""The character panel: the viewed character's sheet, in a column beside the story.

It shows whatever :class:`~aimaginarium.ui.character.CharacterView` it is given and leaves out every section
that has nothing in it, so a character that is little known (another party member, say) shows little.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

from ..character import ABILITIES, COINS, CharacterView, modifier, signed
from .hanging import Hanging
from .party import CONTROLLER_TAGS, hp_bar, hp_style

SECTIONS = (
    ("skills", "Skills", False),
    ("proficiencies", "Proficiencies", False),
    ("equipment", "Equipment", False),
    ("inventory", "Inventory", True),
    ("features", "Features", False),
    ("spells", "Spells", False),
    ("conditions", "Conditions", True),
    ("about", "About", False),
)
"""Section id, title and whether it starts open. The set grows with what is known about a character."""


class CharacterPanel(VerticalScroll):
    """Renders a :class:`CharacterView`. Call :meth:`show` whenever the viewed character or its data changes."""

    COMPONENT_CLASSES = {"characterpanel--dim", "characterpanel--hp-high", "characterpanel--hp-mid", "characterpanel--hp-low",
                         "characterpanel--accent"}
    DEFAULT_CSS = """
    CharacterPanel { width: 40; padding: 0 1; background: $surface; }
    CharacterPanel Static { height: auto; }
    CharacterPanel #cp-name { text-style: bold; color: $primary; margin-top: 1; }
    CharacterPanel #cp-viewing { color: $system; text-style: italic; }
    CharacterPanel #cp-abilities, CharacterPanel #cp-core, CharacterPanel #cp-hp { margin-top: 1; }
    CharacterPanel Collapsible { margin-top: 1; padding: 0; border-top: none; background: $surface; }
    CharacterPanel CollapsibleTitle { color: $secondary; text-style: bold; padding: 0 1; }
    CharacterPanel Collapsible > Contents { padding: 0 1; }
    CharacterPanel > .characterpanel--dim { color: $system; }
    CharacterPanel > .characterpanel--accent { color: $accent; }
    CharacterPanel > .characterpanel--hp-high { color: $success; }
    CharacterPanel > .characterpanel--hp-mid { color: $warning; }
    CharacterPanel > .characterpanel--hp-low { color: $error; }
    """

    def compose(self) -> ComposeResult:
        for part in ("name", "viewing", "identity", "core", "hp", "xp", "abilities", "empty"):
            yield Static(id=f"cp-{part}", markup=False)
        for key, title, open_ in SECTIONS:
            yield Collapsible(Static(id=f"cp-{key}", markup=False), title=title, collapsed=not open_, id=f"cp-sec-{key}")

    view: CharacterView | None = None
    """The character last shown."""

    def _set(self, part: str, content: Text | Table | str) -> None:
        widget = self.query_one(f"#cp-{part}", Static)
        widget.update(content)
        widget.display = bool(content) if isinstance(content, (str, Text)) else True

    def _section(self, key: str, title: str, lines: list[RenderableType], count: int | None = None) -> None:
        section = self.query_one(f"#cp-sec-{key}", Collapsible)
        section.display = bool(lines)
        section.title = f"{title} ({count})" if count else title
        self.query_one(f"#cp-{key}", Static).update(Group(*lines))

    def show(self, view: CharacterView | None) -> None:
        """Shows this character, or an empty panel for ``None``."""
        if view is None:
            view = CharacterView(name="")
        self.view = view
        dim = self.get_component_rich_style("characterpanel--dim")
        accent = self.get_component_rich_style("characterpanel--accent")

        tag = CONTROLLER_TAGS[view.controller]
        self._set("name", Text(view.name + (f"  [{tag}]" if tag else "")))
        self._set("viewing", Text("" if view.mine or not view.name else "Viewing, not your character"))
        self._set("identity", Text(view.identity, style=dim))

        core = Text()
        for label, value in (("AC", view.ac), ("PROF", None if view.proficiency is None else signed(view.proficiency))):
            if value is not None:
                core.append(f"{label} ", style=dim).append(f"{value}   ", style="bold")
        if view.inspiration:
            core.append("✦ Inspiration", style=accent)
        self._set("core", core)

        hp = Text()
        if view.hp is not None and view.max_hp:
            hp.append("HP ", style=dim).append(hp_bar(view), style=self.get_component_rich_style(f"characterpanel--{hp_style(view)}"))
            if view.temp_hp:
                hp.append(f"  +{view.temp_hp} temp", style=dim)
        self._set("hp", hp)

        xp = Text()
        if view.xp is not None:
            xp.append("XP ", style=dim).append(f"{view.xp:,}" + (f" / {view.xp_next:,}" if view.xp_next else ""))
        self._set("xp", xp)

        if view.abilities:
            grid = Table.grid(expand=True)
            for _ in ABILITIES:
                grid.add_column(justify="center")
            known = [a for a in ABILITIES if a in view.abilities]
            grid.add_row(*(Text(a.upper(), style=dim) for a in known))
            grid.add_row(*(Text(str(view.abilities[a]), style="bold") for a in known))
            grid.add_row(*(Text(signed(modifier(view.abilities[a])), style=dim) for a in known))
            self._set("abilities", grid)
        else:
            self._set("abilities", "")

        width = max((len(name) for name in view.skills), default=0)
        self._section("skills", "Skills", [Text.assemble(f"{name.title():<{width}}  ", (signed(bonus), "bold"))
                                           for name, bonus in sorted(view.skills.items())])
        self._section("proficiencies", "Proficiencies", [Text(p) for p in view.proficiencies])
        self._section("equipment", "Equipment", [Text(e) for e in view.equipment])
        inventory = [Text(" ").join(Text.assemble((c.upper(), dim), f" {view.coins[c]}") for c in COINS if c in view.coins)]
        inventory = inventory if view.coins else []
        for item in view.inventory:
            inventory.append(Group(Text(item.name), *([Hanging(Text(item.description, style=dim), "  ")] if item.description else [])))
        self._section("inventory", "Inventory", inventory, len(view.inventory))
        self._section("features", "Features", [Text(f) for f in view.features])
        self._section("spells", "Spells", [Text(s) for s in view.spells], len(view.spells))
        self._section("conditions", "Conditions", [Text(s) for s in view.statuses])
        about: list[RenderableType] = [Text(view.description)] if view.description else []
        about += [Hanging(Text(fact), "• ") for fact in view.facts]
        self._section("about", "About", about)

        nothing = not (view.identity or view.ac is not None or view.hp is not None or view.abilities or view.xp is not None
                       or any(self.query_one(f"#cp-sec-{k}").display for k, _, _ in SECTIONS))
        self._set("empty", Text("Nothing more is known about this character." if nothing and view.name else "", style=dim))
