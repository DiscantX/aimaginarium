"""Loading spinner for terminal and textual interfaces."""

from __future__ import annotations

import random
import sys
import threading
import time
from typing import IO, Any, Optional, Sequence

DEFAULT_MESSAGES = (
    "Consulting the dark oracle...",
    "Rolling hidden 20-sided dice...",
    "Inspecting ancient scrolls...",
    "Summoning the dungeon master...",
)

SPIN_SYMBOLS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """An animated loading spinner with playful messages for LLM generation."""

    def __init__(
        self,
        messages: Optional[Sequence[str]] = None,
        interval: float = 0.08,
        stream: Optional[IO[str]] = None,
    ) -> None:
        self.messages = messages or DEFAULT_MESSAGES
        self.interval = interval
        self.stream = stream or sys.stdout
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _animate(self) -> None:
        msg = random.choice(self.messages)
        symbol_idx = 0
        while not self._stop_event.is_set():
            symbol = SPIN_SYMBOLS[symbol_idx % len(SPIN_SYMBOLS)]
            try:
                self.stream.write(f"\r\033[K \033[35m{symbol}\033[0m {msg}")
                self.stream.flush()
            except Exception:
                pass
            symbol_idx += 1
            time.sleep(self.interval)

    def start(self) -> Spinner:
        """Starts the spinner animation thread."""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stops the spinner animation and clears the line."""
        if not self._stop_event.is_set():
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            self._thread = None
            try:
                self.stream.write("\r\033[K\033[0m")
                self.stream.flush()
            except Exception:
                pass

    def __enter__(self) -> Spinner:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    async def __aenter__(self) -> Spinner:
        return self.start()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
