"""Test suite for LLM cost estimation across models and tiers."""

from aimaginarium.llm import Usage, estimate_cost, DEFAULT_PRICING, ModelPricing


def test_gemini_flash_lite_cost():
    """Test cost estimation for gemini-3.5-flash-lite with prompt, cached, and output tokens."""
    # prompt_tokens=1,000,000 total prompt tokens, of which 500,000 are cached.
    # Non-cached prompt tokens = 1,000,000 - 500,000 = 500,000 -> 0.5 * $0.30 = $0.15
    # Cached tokens = 500,000 -> 0.5 * $0.03 = $0.015
    # Output tokens = 100,000 -> 0.1 * $2.50 = $0.25
    # Total = 0.15 + 0.015 + 0.25 = $0.415
    usage = Usage(
        prompt_tokens=1_000_000,
        cached_tokens=500_000,
        output_tokens=100_000,
    )
    estimate = estimate_cost("gemini-3.5-flash-lite", usage)
    
    assert abs(estimate.input_cost - 0.15) < 1e-6
    assert abs(estimate.cached_cost - 0.015) < 1e-6
    assert abs(estimate.output_cost - 0.25) < 1e-6
    assert abs(estimate.total_cost - 0.415) < 1e-6
    assert estimate.currency == "USD"


def test_free_tier_cost():
    """Test that free tier enforcement results in $0 cost."""
    usage = Usage(
        prompt_tokens=10_000_000,
        cached_tokens=5_000_000,
        output_tokens=2_000_000,
    )
    estimate = estimate_cost("gemini-3.5-flash-lite", usage, free_tier=True)
    
    assert estimate.input_cost == 0.0
    assert estimate.cached_cost == 0.0
    assert estimate.output_cost == 0.0
    assert estimate.total_cost == 0.0


def test_local_model_cost():
    """Test that local models (Ollama) have zero cost."""
    usage = Usage(
        prompt_tokens=50_000,
        cached_tokens=None,
        output_tokens=10_000,
    )
    estimate = estimate_cost("local", usage)
    
    assert estimate.total_cost == 0.0


def test_custom_pricing_catalog():
    """Test cost estimation with a custom pricing catalog."""
    catalog = {
        "custom-model": ModelPricing(
            input_price_per_m=1.00,
            output_price_per_m=10.00,
            cached_input_price_per_m=0.10,
        )
    }
    usage = Usage(
        prompt_tokens=1_000_000,
        cached_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    estimate = estimate_cost("custom-model", usage, pricing_catalog=catalog)
    
    assert abs(estimate.input_cost - 0.0) < 1e-6  # prompt_tokens (1M) - cached_tokens (1M) = 0
    assert abs(estimate.cached_cost - 0.10) < 1e-6
    assert abs(estimate.output_cost - 10.00) < 1e-6
    assert abs(estimate.total_cost - 10.10) < 1e-6
