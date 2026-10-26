"""Pure token cost calculation logic (Principle 6: No hardcoded model IDs or prices)."""

from __future__ import annotations


def calculate_llm_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    prices_by_model: dict[str, dict[str, float]],
) -> float:
    """Compute the USD cost for an LLM call using configured per-1M-token rates.

    Raises KeyError if `model` is not present in `prices_by_model` and fallback
    pricing is not configured, ensuring unpriced models are caught early.
    """
    if prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError("Token counts must be non-negative integers.")
    if model not in prices_by_model:
        raise KeyError(
            f"Model '{model}' has no pricing entry in MODEL_PRICES_JSON or config/models.yaml."
        )
    rates = prices_by_model[model]
    input_per_1m = float(rates.get("input_per_1m", 0.0))
    output_per_1m = float(rates.get("output_per_1m", 0.0))
    cost = (prompt_tokens / 1_000_000.0) * input_per_1m + (
        completion_tokens / 1_000_000.0
    ) * output_per_1m
    return round(cost, 8)
