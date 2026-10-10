"""Wrapped text with a hanging indent.

A hanging indent cannot be written into a string: a widget wraps the string to its width afterwards, and
wrapping only knows characters, so a prefix typed into the string applies to the first visual line only.
:class:`Hanging` makes the prefix a property of the layout instead: it wraps the text to the width left
after the prefix, then puts the prefix on *every* visual line. Use it for any text that can wrap and
needs an indent, a bullet or a gutter (never build that layout into a string).
"""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text


class Hanging:
    """A block of text whose lines all carry a prefix; the first may differ from the rest.

    Args:
        content: The text. Real newlines start new logical lines, each wrapped on its own and each
            carrying the ``rest`` prefix (only the very first visual line gets ``first``).
        first: Prefix of the first visual line (a bullet, an indent, a gutter).
        rest: Prefix of every other visual line. Defaults to blanks as wide as ``first``, so the
            wrapped text hangs under the text's own first character.
    """

    def __init__(self, content: Text | str, first: Text | str = "", rest: Text | str | None = None) -> None:
        self.content = content if isinstance(content, Text) else Text(content)
        self.first = first if isinstance(first, Text) else Text(first)
        if rest is None:
            rest = " " * self.first.cell_len
        self.rest = rest if isinstance(rest, Text) else Text(rest)

    @classmethod
    def gutter(cls, content: Text | str, gutter: Text | str) -> Hanging:
        """A block with the same prefix on every line, e.g. a ``│ `` gutter."""
        return cls(content, gutter, gutter)

    @property
    def plain(self) -> str:
        """The block unwrapped, as plain text: what it says, with no layout applied."""
        lines = self.content.plain.split("\n")
        prefixes = [self.first.plain] + [self.rest.plain] * (len(lines) - 1)
        return "\n".join(prefix + line for prefix, line in zip(prefixes, lines))

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = max(1, options.max_width - max(self.first.cell_len, self.rest.cell_len))
        for number, line in enumerate(self.content.wrap(console, width, overflow="fold")):
            yield Text.assemble(self.first if number == 0 else self.rest, line)


class Blocks:
    """Hanging blocks one under another; :attr:`plain` is the whole thing unwrapped (what copy and tests read)."""

    def __init__(self, blocks: list[Hanging]) -> None:
        self.blocks = blocks

    @property
    def plain(self) -> str:
        return "\n".join(block.plain for block in self.blocks)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from self.blocks
