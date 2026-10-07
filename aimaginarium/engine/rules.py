"""Dice and a minimal d20 rule set for the prototype.

This is the generic stand-in until ruleset plugins exist (5e comes from the
SRD data). The engine only needs two things from a ruleset: a modifier for a
skill, and the classification of a roll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from ..world import Entity

CLASSES = ("critical_failure", "failure", "narrow_success", "success", "critical_success")


@dataclass(frozen=True)
class Roll:
    """The result of one check.

    Attributes:
        skill: What was tested.
        die: The d20 as rolled.
        modifier: Added to the die.
        total: Die plus modifier.
        difficulty: The number to meet.
        margin: Total minus difficulty.
        classification: One of :data:`CLASSES`.
    """

    skill: str
    die: int
    modifier: int
    total: int
    difficulty: int
    margin: int
    classification: str


class D20Rules:
    """Roll a d20, add the skill modifier, compare with the difficulty.

    A natural 1 or 20 is a critical result; otherwise a total that meets the
    difficulty by less than ``narrow`` is a narrow success.
    """

    def __init__(self, rng: Optional[random.Random] = None, narrow: int = 3):
        """Initialises the rules.

        Args:
            rng: Source of dice; pass a seeded one for reproducible runs.
            narrow: A success by fewer points than this is narrow.
        """
        self._rng = rng or random.Random()
        self.narrow = narrow

    def modifier(self, character: Entity, skill: str) -> int:
        """Reads a skill bonus from ``data.sheet.skills`` (zero if the sheet has none)."""
        return int(character.data.get("sheet", {}).get("skills", {}).get(skill.lower(), 0))

    def roll(self, character: Entity, skill: str, difficulty: int) -> Roll:
        """Rolls a check for a character.

        Args:
            character: Who is rolling.
            skill: What is being tested.
            difficulty: The number to meet.

        Returns:
            The roll, with its classification.
        """
        die = self._rng.randint(1, 20)
        modifier = self.modifier(character, skill)
        total = die + modifier
        margin = total - difficulty
        if die == 1:
            kind = "critical_failure"
        elif die == 20:
            kind = "critical_success"
        elif margin < 0:
            kind = "failure"
        else:
            kind = "narrow_success" if margin < self.narrow else "success"
        return Roll(skill, die, modifier, total, difficulty, margin, kind)
