"""The structured parts of the model's replies (narration is added by the narration plan)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, get_args

from pydantic import BaseModel, BeforeValidator, Field


Tier = Literal["very_easy", "easy", "medium", "hard", "very_hard", "nearly_impossible"]
Effect = Literal["easier", "harder"]
Size = Literal["small", "medium", "large"]


def _choice(allowed: tuple[str, ...], default: str):
    """Returns a validator that normalises a value to one of ``allowed``, else ``default``.

    Weaker models write "Very Hard" or "moderate"; losing a turn over that would be
    worse than a sensible default. The JSON schema still lists the exact values.
    """

    def normalise(value: Any) -> Any:
        text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        return text if text in allowed else default

    return BeforeValidator(normalise)


class Factor(BaseModel):
    """A condition that makes a task easier or harder than its tier suggests.

    Attributes:
        what: The condition in the fiction, such as "rain-slick stones".
        effect: Whether it helps or hinders.
        size: How much.
    """

    what: str
    effect: Annotated[Effect, _choice(get_args(Effect), "harder")]
    size: Annotated[Size, _choice(get_args(Size), "small")]


class CheckRequest(BaseModel):
    """Asks for a dice check before the outcome is narrated.

    The narrator judges how hard the task is in the fiction; the ruleset turns
    that into a number, so no number comes from the model.

    Attributes:
        skill: What is being tested, such as ``stealth``.
        tier: How hard the task is for a capable person, before the factors.
        factors: Conditions that shift it; only ones actually present.
        reason: Why failure or success would matter in the story.
    """

    skill: str
    tier: Annotated[Tier, _choice(get_args(Tier), "medium")]
    factors: list[Factor] = Field(default_factory=list)
    reason: str = ""


class TurnReply(BaseModel):
    """Everything in a call-1 reply besides the narration.

    Attributes:
        check: A check request, if the outcome is uncertain and matters.
        changes: Proposed state changes (see ``aimaginarium.world.changes``); leave empty when a check is requested.
    """

    check: Optional[CheckRequest] = None
    changes: list[dict[str, Any]] = Field(default_factory=list)


class OutcomeReply(BaseModel):
    """Everything in a call-2 reply besides the narration.

    Attributes:
        changes: Proposed state changes that follow from the roll.
    """

    changes: list[dict[str, Any]] = Field(default_factory=list)


class RepairReply(BaseModel):
    """A corrected set of changes, after the engine rejected a proposal.

    Attributes:
        changes: The corrected changes; empty if none should be made.
    """

    changes: list[dict[str, Any]] = Field(default_factory=list)
