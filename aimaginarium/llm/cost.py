"""Cost estimation for LLM requests across providers, with Gemini-first support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional
from .base import Usage


@dataclass(frozen=True)
class ModelPricing:
    """Pricing rates per 1 million tokens in USD.

    Attributes:
        input_price_per_m: Cost per 1M input (prompt) tokens.
        output_price_per_m: Cost per 1M output (generated) tokens (including thinking tokens).
        cached_input_price_per_m: Cost per 1M cached prompt tokens.
    """

    input_price_per_m: float = 0.30
    output_price_per_m: float = 2.50
    cached_input_price_per_m: float = 0.03


# Default pricing catalog (Gemini 3.5 Flash-Lite paid tier defaults, local models at $0)
DEFAULT_PRICING: dict[str, ModelPricing] = {
    "gemini-3.5-flash-lite": ModelPricing(
        input_price_per_m=0.30,
        output_price_per_m=2.50,
        cached_input_price_per_m=0.03,
    ),
    "gemini-3.5-flash": ModelPricing(
        input_price_per_m=0.30,
        output_price_per_m=2.50,
        cached_input_price_per_m=0.03,
    ),
    "gemini-3.5-pro": ModelPricing(
        input_price_per_m=1.25,
        output_price_per_m=5.00,
        cached_input_price_per_m=0.125,
    ),
    "local": ModelPricing(
        input_price_per_m=0.0,
        output_price_per_m=0.0,
        cached_input_price_per_m=0.0,
    ),
}


@dataclass(frozen=True)
class CostEstimate:
    """Estimated cost breakdown for an LLM call.

    Attributes:
        input_cost: Cost of non-cached prompt tokens in USD.
        cached_cost: Cost of cached prompt tokens in USD.
        output_cost: Cost of output tokens in USD.
        total_cost: Total estimated cost in USD.
        currency: Currency code (default "USD").
    """

    input_cost: float = 0.0
    cached_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"


def estimate_cost(
    model: str,
    usage: Usage,
    pricing_catalog: Optional[Mapping[str, ModelPricing]] = None,
    free_tier: bool = False,
) -> CostEstimate:
    """Calculates the estimated cost of an LLM call based on token usage and model pricing.

    Args:
        model: Model name or identifier.
        usage: Token usage figures (:class:`Usage`).
        pricing_catalog: Optional custom mapping of model names to :class:`ModelPricing`.
        free_tier: If True, cost is zero regardless of model pricing.

    Returns:
        A :class:`CostEstimate` detailing breakdown and total cost in USD.
    """
    if free_tier:
        return CostEstimate()

    catalog = pricing_catalog if pricing_catalog is not None else DEFAULT_PRICING

    pricing = catalog.get(model)
    if pricing is None:
        if "local" in model.lower() or "ollama" in model.lower():
            pricing = catalog.get("local", ModelPricing(0.0, 0.0, 0.0))
        else:
            pricing = catalog.get("gemini-3.5-flash-lite", ModelPricing(0.30, 2.50, 0.03))

    output_tokens = max(0, usage.output_tokens)
    cached = usage.cached_tokens if usage.cached_tokens is not None else 0
    non_cached_prompt = max(0, usage.prompt_tokens - cached)

    input_cost = (non_cached_prompt / 1_000_000.0) * pricing.input_price_per_m
    cached_cost = (cached / 1_000_000.0) * pricing.cached_input_price_per_m
    output_cost = (output_tokens / 1_000_000.0) * pricing.output_price_per_m
    total_cost = input_cost + cached_cost + output_cost

    return CostEstimate(
        input_cost=input_cost,
        cached_cost=cached_cost,
        output_cost=output_cost,
        total_cost=total_cost,
    )
