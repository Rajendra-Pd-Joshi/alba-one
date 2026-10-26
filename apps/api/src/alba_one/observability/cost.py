"""Span Cost Calculator, Token Estimator & Historical Recompute Engine (`observability/cost.py`).

Per Phase 9 User Answer 1:
- Computed from `config/models.yaml` prices at write time and stamped with `price_table_version`.
- Display currency conversion (`USD` -> `JPY`) uses the configured, dated rate (`fx_usdjpy` and
  `fx_rate_date` in `config/models.yaml`), NEVER a live network fetch.
- Unpriced models or tools get `cost_amount = None` (`NULL`) and `cost_estimated = True` — NEVER `0.0`!
- Cache hits (`cache_hit=True` or `status="cache_hit"`) cost `0.0` (`cost_estimated = False`) and are recorded.
- Failed and retried calls still count toward cost.
- Uses provider-reported token counts when available; if absent, estimates tokens deterministically
  and flags `tokens_estimated = True`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from alba_one.kb.indexer import find_repo_root
from alba_one.observability.spans import SpanRecord


@dataclass(frozen=True)
class PriceTableConfig:
    """Loaded pricing and dated FX metadata from `config/models.yaml`."""

    price_table_version: str
    cost_currency: str
    display_currency: str
    fx_usdjpy: float
    fx_rate_date: str
    models: dict[str, dict[str, float]]


def load_price_table(config_path: str | Path | None = None) -> PriceTableConfig:
    """Load `config/models.yaml` pricing table and dated FX rate."""
    path = Path(config_path) if config_path else (find_repo_root() / "config" / "models.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    models_raw = raw.get("models", {})
    models_map: dict[str, dict[str, float]] = {}
    for m_name, spec in models_raw.items():
        if "input_per_1m_usd" in spec or "output_per_1m_usd" in spec:
            models_map[str(m_name)] = {
                "input_per_1m_usd": float(spec.get("input_per_1m_usd", 0.0)),
                "output_per_1m_usd": float(spec.get("output_per_1m_usd", 0.0)),
            }
    return PriceTableConfig(
        price_table_version=str(raw.get("price_table_version", "2026-10-24.v1")),
        cost_currency=str(raw.get("cost_currency", "USD")),
        display_currency=str(raw.get("display_currency", "JPY")),
        fx_usdjpy=float(raw.get("fx_usdjpy", 151.45)),
        fx_rate_date=str(raw.get("fx_rate_date", "2026-10-24")),
        models=models_map,
    )


def resolve_tokens(
    *,
    reported_tokens_in: int | None,
    reported_tokens_out: int | None,
    prompt_text: str | None = None,
    output_text: str | None = None,
) -> tuple[int, int, bool]:
    """Use provider-reported token counts if present; otherwise estimate and flag `tokens_estimated=True`."""
    if reported_tokens_in is not None and reported_tokens_out is not None:
        return int(reported_tokens_in), int(reported_tokens_out), False
    est_in = int(reported_tokens_in) if reported_tokens_in is not None else max(1, len(prompt_text or "") // 4)
    est_out = int(reported_tokens_out) if reported_tokens_out is not None else (max(1, len(output_text) // 4) if output_text else 0)
    return est_in, est_out, True


def compute_call_cost(
    *,
    model_or_tool: str,
    tokens_in: int,
    tokens_out: int,
    cache_hit: bool = False,
    tokens_estimated: bool = False,
    price_table: PriceTableConfig | None = None,
) -> tuple[float | None, str, str, bool]:
    """Return `(cost_amount, cost_currency, price_table_version, cost_estimated)`."""
    pt = price_table or load_price_table()
    if cache_hit:
        return 0.0, pt.cost_currency, pt.price_table_version, False

    entry = pt.models.get(model_or_tool)
    if entry is None:
        # Unpriced model or tool MUST get cost_amount=None (NULL) and cost_estimated=True, NEVER 0.0!
        return None, pt.cost_currency, pt.price_table_version, True

    in_cost = (max(0, tokens_in) / 1_000_000.0) * entry["input_per_1m_usd"]
    out_cost = (max(0, tokens_out) / 1_000_000.0) * entry["output_per_1m_usd"]
    total = round(in_cost + out_cost, 8)
    return total, pt.cost_currency, pt.price_table_version, bool(tokens_estimated)


def convert_usd_to_configured_jpy(
    amount_usd: float | None,
    *,
    price_table: PriceTableConfig | None = None,
) -> dict[str, Any]:
    """Convert USD cost to JPY using the configured, dated FX rate (never a live fetch)."""
    pt = price_table or load_price_table()
    if amount_usd is None:
        return {"cost_usd": None, "cost_jpy": None, "fx_usdjpy": pt.fx_usdjpy, "fx_rate_date": pt.fx_rate_date}
    return {
        "cost_usd": round(amount_usd, 6),
        "cost_jpy": round(amount_usd * pt.fx_usdjpy, 2),
        "fx_usdjpy": pt.fx_usdjpy,
        "fx_rate_date": pt.fx_rate_date,
    }


def recompute_spans_cost(
    spans: list[SpanRecord],
    *,
    price_table: PriceTableConfig | None = None,
) -> dict[str, int]:
    """Recompute `cost_amount` and `price_table_version` across historical spans when prices change."""
    pt = price_table or load_price_table()
    updated = 0
    unpriced = 0
    for sp in spans:
        cost_amt, cur, ver, est = compute_call_cost(
            model_or_tool=sp.model_or_tool,
            tokens_in=sp.tokens_in,
            tokens_out=sp.tokens_out,
            cache_hit=sp.cache_hit or sp.status == "cache_hit",
            tokens_estimated=sp.tokens_estimated,
            price_table=pt,
        )
        sp.cost_amount = cost_amt
        sp.cost_currency = cur
        sp.price_table_version = ver
        sp.cost_estimated = est
        updated += 1
        if cost_amt is None:
            unpriced += 1
    return {"spans_recomputed": updated, "unpriced_calls": unpriced, "price_table_version": pt.price_table_version}
