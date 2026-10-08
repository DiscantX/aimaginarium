"""ANSI color utilities and stylesheet configuration for terminal UI."""

from __future__ import annotations

import functools
from typing import Any, Callable, Mapping, Optional

COLORS: dict[str, str] = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_black": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
}
# # Original style -- too dark, don't use
# DEFAULT_STYLES: dict[str, str] = {
#     "narration": "dim",
#     "indicator": "magenta",
#     "player": "green",
#     "muted": "bright_black",
# }

# # Classic Roguelike
# DEFAULT_STYLES: dict[str, str] = {
#     "narration": "bright_white",  # High contrast, clean narrative text
#     "indicator": "bright_yellow", # For prompt anchors like > or [Choice]
#     "player": "green",            # What the player types stays distinct
#     "muted": "dim",               # Keeps system logs/meta-text quiet
# }

# Arcane Spellbook
DEFAULT_STYLES: dict[str, str] = {
    "narration": "white",          # Soft white (slightly dimmer than bright_white)
    "indicator": "bright_cyan",    # High visibility magic prompts
    "player": "bright_magenta",    # Elegant, mystic player input color
    "muted": "bright_black",       # Perfect "dark gray" for hidden details
}

# # Grim & Perilous
# DEFAULT_STYLES: dict[str, str] = {
#     "narration": "bright_white",   # Pure clarity for environmental layout
#     "indicator": "bright_red",     # Threat indicators or combat prompts
#     "player": "yellow",            # Warm torchlight color for active input
#     "muted": "dim",                # Blends secondary info away
# }


class Stylesheet:
    """Manages color styles, loading overrides from configuration dictionaries."""

    def __init__(self, overrides: Optional[Mapping[str, Any]] = None) -> None:
        """Initialises the stylesheet with optional overrides.

        Args:
            overrides: Optional mapping of style keys to color/style names.
        """
        self._styles = dict(DEFAULT_STYLES)
        if overrides:
            styles_cfg = overrides.get("styles", overrides)
            for k, v in styles_cfg.items():
                if k in self._styles and isinstance(v, str):
                    self._styles[k] = v

    def get(self, key: str) -> str:
        """Returns the color name mapped to a style key."""
        return self._styles.get(key, "reset")

    def colorize(self, text: str, key: str) -> str:
        """Colorises text using the color mapped to the given style key, ensuring reset."""
        if not text:
            return ""
        color_name = self.get(key)
        code = COLORS.get(color_name, COLORS["reset"])
        reset = COLORS["reset"]
        return f"{code}{text}{reset}"


# Global default stylesheet instance
_active_stylesheet = Stylesheet()


def set_stylesheet(overrides: Optional[Mapping[str, Any]] = None) -> None:
    """Sets the global active stylesheet."""
    global _active_stylesheet
    _active_stylesheet = Stylesheet(overrides)


def colorize(text: str, color_or_key: str) -> str:
    """Colorises text using either a direct color name or style key from the active stylesheet."""
    if not text:
        return ""
    if color_or_key in COLORS:
        code = COLORS[color_or_key]
        return f"{code}{text}{COLORS['reset']}"
    return _active_stylesheet.colorize(text, color_or_key)


def styled(color_or_key: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator that colorises the string return value of a function."""
    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            result = func(*args, **kwargs)
            return colorize(result, color_or_key)
        return wrapper
    return decorator
