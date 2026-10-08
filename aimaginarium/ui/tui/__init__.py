"""The Textual terminal UI, a first-class client of the internal API."""

import argparse
from typing import Optional, Sequence

from ...llm import ConfigError
from ..bootstrap import Runtime, add_common_arguments
from .app import GameApp

__all__ = ["GameApp", "main"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs the Textual UI (``python -m aimaginarium``)."""
    import sys

    parser = argparse.ArgumentParser(description="Play AImaginarium in the terminal.")
    add_common_arguments(parser)
    args = parser.parse_args(argv)
    app: Optional[GameApp] = None

    def notify(text: str) -> None:
        if app is not None:
            app.notify(text, timeout=6)

    try:
        runtime = Runtime.open(args, notify=notify)
    except ConfigError as exc:
        print(f"configuration problem: {exc}", file=sys.stderr)
        return 2
    try:
        app = GameApp(runtime.session, opening=not runtime.begun)
        app.run()
    finally:
        runtime.close()
    return app.return_code or 0
