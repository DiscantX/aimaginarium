"""The narration plan: a reply's paragraphs as discrete, ordered slots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from pydantic import BaseModel, Field, create_model

from .fragments import PromptError


@dataclass(frozen=True)
class Slot:
    """A run of paragraphs with one job.

    Attributes:
        id: Name of the slot, such as ``world``.
        instruction: What these paragraphs should do.
        min: Fewest paragraphs.
        max: Most paragraphs.
    """

    id: str
    instruction: str
    min: int = 1
    max: Optional[int] = None

    def __post_init__(self):
        if self.max is None:
            object.__setattr__(self, "max", self.min)
        if not 1 <= self.min <= self.max:
            raise PromptError(f"slot {self.id!r}: need 1 <= min <= max, got {self.min} and {self.max}")


class NarrationPlan:
    """An ordered list of slots.

    Only the last slot may vary in length, so the slot of a paragraph follows
    from its position alone.
    """

    def __init__(self, slots: Sequence[Slot]):
        """Initialises the plan.

        Args:
            slots: The slots in order. At least one.

        Raises:
            PromptError: If there are none, or a slot other than the last varies.
        """
        if not slots:
            raise PromptError("a narration plan needs at least one slot")
        if any(s.min != s.max for s in slots[:-1]):
            raise PromptError("only the last slot of a narration plan may vary in length")
        self.slots = tuple(slots)

    @property
    def min(self) -> int:
        """Returns the fewest paragraphs in a reply."""
        return sum(s.min for s in self.slots)

    @property
    def max(self) -> int:
        """Returns the most paragraphs in a reply."""
        return sum(s.max for s in self.slots)

    def slot_of(self, index: int) -> Slot:
        """Returns the slot a paragraph belongs to.

        Args:
            index: Position of the paragraph, from zero.
        """
        start = 0
        for slot in self.slots:
            if index < start + slot.max:
                return slot
            start += slot.max
        return self.slots[-1]

    def describe(self) -> str:
        """Returns the plan as instructions for the model."""
        lines = [f"Write the narration as {self._count(self.min, self.max)}, in this order:"]
        start = 1
        for slot in self.slots:
            end = start + slot.max - 1
            span = f"Paragraph {start}" if start == end else f"Paragraphs {start}-{end}"
            lines.append(f"- {span} ({slot.id}): {slot.instruction}")
            start = end + 1
        return "\n".join(lines)

    @staticmethod
    def _count(low: int, high: int) -> str:
        """Words for a paragraph count."""
        return f"exactly {low} paragraphs" if low == high else f"{low} to {high} paragraphs"

    def reply_model(self, base: Optional[type[BaseModel]] = None) -> type[BaseModel]:
        """Builds the reply schema, with ``narration`` as its first field.

        Args:
            base: Model whose fields follow the narration (changes, check request, ...).

        Returns:
            A model whose ``narration`` is a list of paragraphs sized by the plan.
        """
        fields = {"narration": (list[str], Field(min_length=self.min, max_length=self.max))}
        for name, info in (base.model_fields if base else {}).items():
            fields[name] = (info.annotation, info)
        return create_model("Reply", **fields)
