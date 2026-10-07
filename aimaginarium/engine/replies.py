"""The structured parts of the model's replies (narration is added by the narration plan)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    """Asks for a dice check before the outcome is narrated.

    Attributes:
        skill: What is being tested, such as ``stealth``.
        difficulty: The number the total must meet.
        reason: Why failure or success would matter in the story.
    """

    skill: str
    difficulty: int = Field(ge=1, le=40)
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
