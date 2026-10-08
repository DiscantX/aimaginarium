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
from .replies import CheckRequest

TIERS = {"very_easy": 5, "easy": 10, "medium": 15, "hard": 20, "very_hard": 25, "nearly_impossible": 30}
SIZES = {"small": 1, "medium": 2, "large": 4}
MAX_ADJUSTMENT = 6
CLASSES = ("critical_failure", "failure", "narrow_success", "success", "critical_success")


@dataclass(frozen=True)
class Ruling:
    """How a check's difficulty was worked out.

    Attributes:
        tier: The narrator's tier.
        base: The tier's base number.
        adjustments: Each factor with its signed effect on the number.
        adjustment: The total applied (the sum, limited to the maximum).
        difficulty: The number the total must meet.
    """

    tier: str
    base: int
    adjustments: tuple[tuple[str, int], ...]
    adjustment: int
    difficulty: int

    def as_payload(self) -> dict:
        """Returns the breakdown for the event log."""
        return {"base": self.base, "adjustments": [{"what": w, "delta": d} for w, d in self.adjustments],
                "adjustment": self.adjustment, "difficulty": self.difficulty}


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

    def rule(self, check: CheckRequest) -> Ruling:
        """Turns a tier and factors into a difficulty number.

        The tier gives the base; each factor moves it by its size (harder up,
        easier down); the total move is limited so a pile of factors cannot
        turn a hard task trivial; the result stays between 1 and 40.

        Args:
            check: The narrator's request.

        Returns:
            The ruling, with its breakdown.
        """
        base = TIERS[check.tier]
        steps = tuple((f.what, SIZES[f.size] * (1 if f.effect == "harder" else -1)) for f in check.factors)
        total = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, sum(d for _, d in steps)))
        return Ruling(check.tier, base, steps, total, max(1, min(40, base + total)))

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
