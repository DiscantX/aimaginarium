"""Lets ``python -m aimaginarium`` start the game (the Textual UI; ``--cli`` for the plain client)."""

from .ui.launch import main

raise SystemExit(main())
