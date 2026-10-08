"""Starts the right client: the Textual UI by default, the plain terminal client with ``--cli``."""

import sys
from typing import Optional, Sequence

from .cli import main as cli_main


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for ``python -m aimaginarium`` and the ``aimaginarium`` command."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--cli" in args:
        args.remove("--cli")
        return cli_main(args)
    try:
        from .tui import main as tui_main
    except ImportError:
        print("The Textual UI is not installed (pip install \"aimaginarium[tui]\"); starting the plain client.",
              file=sys.stderr)
        return cli_main(args)
    return tui_main(args)
