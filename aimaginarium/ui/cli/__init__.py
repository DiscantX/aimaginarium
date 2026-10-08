"""The plain terminal client: a line-by-line console on the internal API."""

from .client import ask_input, discard_pending_input, main, play, show

__all__ = ["ask_input", "discard_pending_input", "main", "play", "show"]
