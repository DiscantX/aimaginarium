"""Incremental extraction of the narration from a streaming JSON reply.

The model returns one JSON object with the narration as its first field, either
as one string or as a list of paragraph strings. This pulls the narration out
while it is still being generated, so it can be shown to the player at once.
List items are joined with a blank line. It assumes the narration key is the
first one in the object.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from .base import Chunk, StreamEvent

PARAGRAPH_BREAK = "\n\n"
_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
_REPLACEMENT = "\ufffd"


class NarrationExtractor:
    """Feeds on raw JSON text chunks and returns the decoded narration text.

    Attributes:
        done: True once the end of the narration has been seen.
    """

    def __init__(self, key: str = "narration"):
        """Initialises the extractor.

        Args:
            key: Name of the JSON field that holds the narration.
        """
        self._start = re.compile(rf'"{re.escape(key)}"\s*:\s*(\[\s*)?"')
        self._head = ""
        self._pending = ""
        self._started = False
        self._inside = False
        self._array = False
        self.done = False

    def feed(self, text: str) -> str:
        """Consumes the next chunk of the reply.

        Args:
            text: Raw JSON text, split anywhere (even inside an escape).

        Returns:
            The narration decoded from this chunk; empty if there is none yet.
        """
        if self.done:
            return ""
        if not self._started:
            self._head += text
            match = self._start.search(self._head)
            if match is None:
                return ""
            text, self._head = self._head[match.end():], ""
            self._started = self._inside = True
            self._array = match.group(1) is not None
        text, self._pending = self._pending + text, ""
        out: list[str] = []
        while text and not self.done:
            if self._inside:
                decoded, text = self._read_string(text)
                out.append(decoded)
            else:
                text = self._read_gap(text, out)
        return "".join(out)

    def _read_string(self, text: str) -> tuple[str, str]:
        """Decodes string content up to its closing quote, holding back a split escape.

        Returns:
            The decoded text and the unread remainder.
        """
        out: list[str] = []
        i = 0
        while i < len(text):
            char = text[i]
            if char == '"':
                self._inside = False
                self.done = not self._array
                return "".join(out), text[i + 1:]
            if char != "\\":
                out.append(char)
                i += 1
                continue
            decoded, used = _escape(text, i)
            if used == 0:
                self._pending = text[i:]
                break
            out.append(decoded)
            i += used
        return "".join(out), ""

    def _read_gap(self, text: str, out: list[str]) -> str:
        """Skips the commas and spaces between list items, ending at the next item or the list's end."""
        for i, char in enumerate(text):
            if char == '"':
                self._inside = True
                out.append(PARAGRAPH_BREAK)
                return text[i + 1:]
            if char == "]":
                self.done = True
                break
        return ""


def _escape(text: str, i: int) -> tuple[str, int]:
    """Decodes the escape sequence starting at ``text[i]``.

    Returns:
        The decoded characters and the length consumed, or ``("", 0)`` if the
        sequence is not complete yet.
    """
    if i + 1 >= len(text):
        return "", 0
    kind = text[i + 1]
    if kind != "u":
        return _SIMPLE.get(kind, kind), 2
    if i + 6 > len(text):
        return "", 0
    try:
        code = int(text[i + 2:i + 6], 16)
    except ValueError:
        return text[i:i + 2], 2
    if 0xDC00 <= code < 0xE000:
        return _REPLACEMENT, 6
    if not 0xD800 <= code < 0xDC00:
        return chr(code), 6
    rest = text[i + 6:]
    if len(rest) < 6 and "\\u".startswith(rest[:2]):
        return "", 0
    if rest.startswith("\\u"):
        try:
            low = int(rest[2:6], 16)
        except ValueError:
            return _REPLACEMENT, 6
        if 0xDC00 <= low < 0xE000:
            return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)), 12
    return _REPLACEMENT, 6


async def narration_events(events: AsyncIterator[StreamEvent], key: str = "narration") -> AsyncIterator[StreamEvent]:
    """Turns a provider's raw JSON stream into a stream of narration text.

    Args:
        events: The stream from :meth:`LLMProvider.stream`.
        key: Name of the JSON field that holds the narration.

    Yields:
        :class:`Chunk` items holding narration text, then the final response unchanged.
    """
    extractor = NarrationExtractor(key)
    async for event in events:
        if not isinstance(event, Chunk):
            yield event
            continue
        text = extractor.feed(event.text)
        if text:
            yield Chunk(text)
