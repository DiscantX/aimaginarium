"""Player-adjustable settings of the TUI. The config file entry and the palette toggle arrive with the layout work (#68)."""

from dataclasses import dataclass


@dataclass
class Settings:
    """What the player can change.

    Attributes:
        roll_auto_close: Close the roll window by itself after ``roll_hold`` seconds, instead of waiting for the
            player to continue.
        roll_hold: Seconds the finished roll stays up when ``roll_auto_close`` is on.
    """

    roll_auto_close: bool = False
    roll_hold: float = 2.5
