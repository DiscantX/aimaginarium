"""Helpers for testing how text wraps: render a renderable at narrow widths and look at every visual line."""

from rich.console import Console

WIDTHS = (14, 20, 31)


def render_lines(renderable, width: int) -> list[str]:
    """The renderable as the visual lines a ``width``-cell pane would show (trailing blanks removed)."""
    console = Console(width=width, force_terminal=False, color_system=None, legacy_windows=False)
    with console.capture() as capture:
        console.print(renderable, end="")
    return [line.rstrip() for line in capture.get().rstrip("\n").split("\n")]


def assert_hangs(renderable, prefix: str, text: str, widths=WIDTHS) -> None:
    """Asserts that ``text`` wraps at every width and that every visual line of it starts with ``prefix``."""
    for width in widths:
        lines = [line for line in render_lines(renderable, width) if line]
        mine = [line for line in lines if line.startswith(prefix)]
        assert len(mine) > 1, f"{text!r} did not wrap at width {width}: {lines}"
        assert all(line.startswith(prefix) for line in lines[-len(mine):]), f"width {width}: {lines}"
        assert all(len(line) <= width for line in lines), f"width {width}: {lines}"
        assert " ".join(line[len(prefix):] for line in mine).split() == text.split(), f"width {width}: {lines}"
