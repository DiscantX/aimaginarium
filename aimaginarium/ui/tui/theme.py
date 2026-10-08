"""The look of the TUI: a warm dark theme and the semantic roles the widgets are styled with.

Widgets never name colors. They use the roles below (``$narration``, ``$player``, ``$roll``,
``$system``), which a theme may override; any built-in Textual theme falls back to the defaults.
"""

from textual.theme import Theme

CANDLELIT = Theme(
    name="candlelit",
    primary="#d4a94a",
    secondary="#9c7a3c",
    accent="#e8c56d",
    foreground="#e9dcc0",
    background="#0e0d12",
    surface="#16151c",
    panel="#1d1b24",
    success="#7fb069",
    warning="#e0a030",
    error="#cf5c4c",
    dark=True,
    variables={
        "narration": "#e9dcc0",
        "player": "#e8c56d",
        "roll": "#7fc4d9",
        "system": "#8f8872",
    },
)

ROLE_DEFAULTS = {
    "narration": "#dddddd",
    "player": "#e8c56d",
    "roll": "#7fc4d9",
    "system": "#888888",
}
