"""The trace channel: what the engine and the LLM do behind the scenes.

Separate from the game event stream (what the player sees) and from the event
log (what the world remembers). Records go to sinks (a JSON-lines file, the
dev role's live stream) and into a bounded in-memory buffer so a dev client can
ask for what it missed. Tracing must never break a turn, so a failing sink is
dropped silently.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


@dataclass(frozen=True)
class TraceRecord:
    """One traced thing.

    Attributes:
        seq: Position in the trace, starting at 1.
        at: UTC time, ISO 8601 with microseconds.
        turn_id: The turn it happened in, if any.
        kind: What it was, such as ``"llm.call"``.
        payload: Its details (JSON-safe).
    """

    seq: int
    at: str
    turn_id: Optional[int]
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Returns the record as a plain dict."""
        return {"seq": self.seq, "at": self.at, "turn": self.turn_id, "kind": self.kind, "payload": self.payload}


Sink = Callable[[TraceRecord], None]


class Tracer:
    """Collects trace records and hands them to sinks.

    Attributes:
        turn: The turn records are filed under unless one is given. The engine
            sets it when a turn starts, so callbacks from the LLM layer (retries,
            fallbacks), which know nothing of turns, are filed correctly.
    """

    def __init__(self, keep: int = 2000):
        """Initialises the tracer.

        Args:
            keep: Most records kept in memory for :meth:`records`.
        """
        self.turn: Optional[int] = None
        self._seq = 0
        self._buffer: deque[TraceRecord] = deque(maxlen=keep)
        self._sinks: list[Sink] = []

    def add_sink(self, sink: Sink) -> None:
        """Sends every later record to ``sink`` as well."""
        self._sinks.append(sink)

    def emit(self, kind: str, payload: Optional[dict[str, Any]] = None, turn: Optional[int] = None) -> TraceRecord:
        """Records something.

        Args:
            kind: What it is, such as ``"llm.call"``.
            payload: Its details.
            turn: The turn, or None for the current one.

        Returns:
            The record.
        """
        self._seq += 1
        at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        record = TraceRecord(self._seq, at, self.turn if turn is None else turn, kind, payload or {})
        self._buffer.append(record)
        for sink in list(self._sinks):
            try:
                sink(record)
            except Exception:  # a broken sink must not break the game
                self._sinks.remove(sink)
        return record

    def records(self, since: int = 0, limit: int = 200, turn: Optional[int] = None) -> list[TraceRecord]:
        """Returns kept records after ``since``, oldest first.

        Args:
            since: Return only records with a greater sequence number.
            limit: Most records to return.
            turn: If given, only records of that turn.
        """
        found = [r for r in self._buffer if r.seq > since and (turn is None or r.turn_id == turn)]
        return found[:limit]

    def close(self) -> None:
        """Closes every sink that can be closed."""
        for sink in self._sinks:
            getattr(sink, "close", lambda: None)()

    # -- callbacks for the LLM layer (pass these to the provider factory) --

    def on_retry(self, notice: Any) -> None:
        """Traces a retry wait (a ``RetryNotice``)."""
        self.emit("llm.retry", {"attempt": notice.attempt, "delay": notice.delay, "error": str(notice.error)})

    def on_fallback(self, notice: Any) -> None:
        """Traces a move to the next candidate (a ``FallbackNotice``)."""
        self.emit("llm.fallback", {"task": notice.task, "failed": notice.failed, "next": notice.next,
                                   "error": str(notice.error), "cooling_down": notice.cooled})


class JsonlSink:
    """Appends each record to a file as one line of JSON."""

    def __init__(self, path: Path):
        """Opens (creating if needed) the file for appending."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a", encoding="utf-8", buffering=1)

    def __call__(self, record: TraceRecord) -> None:
        self._file.write(json.dumps(record.to_dict(), default=str) + "\n")

    def close(self) -> None:
        """Closes the file."""
        self._file.close()


def _summary(kind: str, p: dict[str, Any]) -> str:
    """One line describing a record."""
    if kind == "llm.call":
        u = p.get("usage", {})
        parts = [p.get("task", "?"), p.get("variant") or "", p.get("model", "?"), f"{u.get('latency', 0):.2f}s"]
        if u.get("time_to_first_token") is not None:
            parts.append(f"first token {u['time_to_first_token']:.2f}s")
        parts.append(f"{u.get('prompt_tokens', 0)} in / {u.get('output_tokens', 0)} out")
        if u.get("cached_tokens"):
            parts.append(f"{u['cached_tokens']} cached")
        return ", ".join(x for x in parts if x)
    if kind == "llm.failed":
        return f"{p.get('task', '?')}: {p.get('error')}"
    if kind == "llm.retry":
        return f"attempt {p['attempt']} failed, waiting {p['delay']:.1f}s: {p['error']}"
    if kind == "llm.fallback":
        return f"{p['failed']} -> {p['next']}" + (" (cooling down)" if p.get("cooling_down") else "") + f": {p['error']}"
    if kind == "reply.invalid":
        return str(p.get("error"))
    if kind == "changes.proposed":
        return f"{len(p['changes'])} change(s)"
    if kind == "changes.accepted":
        return f"{len(p['changes'])} change(s)" + (" (after repair)" if p.get("repaired") else "")
    if kind == "changes.rejected":
        first = p["errors"][0]["message"] if p.get("errors") else "?"
        return f"{len(p['errors'])} error(s)" + (" (repair failed)" if p.get("repaired") else "") + f": {first}"
    if kind == "state.diff":
        return ", ".join(e["kind"] for e in p["events"]) or "no change"
    if kind == "check.workings":
        why = "; ".join(f"{a['what']} {a['delta']:+d}" for a in p.get("adjustments", [])) or "no factors"
        return (f"{p['skill']} {p['tier']} (base {p['base']}, {why}) = difficulty {p['difficulty']}; "
                f"rolled {p['die']} {p['modifier']:+d} = {p['total']} ({p['classification']})")
    return json.dumps(p, default=str)[:120]


def format_timeline(records: Iterable[Any], full: bool = False) -> str:
    """Formats records as a timeline, one line each.

    Args:
        records: Anything with ``kind``, ``payload`` and ``at`` (a :class:`TraceRecord` or an API ``TraceEvent``).
        full: Also print each payload in full (prompts, replies) under its line.

    Returns:
        The text.
    """
    records = list(records)
    if not records:
        return "(nothing traced)"
    start = datetime.fromisoformat(records[0].at)
    lines = []
    for r in records:
        offset = (datetime.fromisoformat(r.at) - start).total_seconds()
        lines.append(f"+{offset:7.3f}s  {r.kind:<17} {_summary(r.kind, r.payload)}")
        if full:
            body = json.dumps(r.payload, indent=2, default=str, ensure_ascii=False)
            lines.append("\n".join("            " + ln for ln in body.splitlines()))
    return "\n".join(lines)
