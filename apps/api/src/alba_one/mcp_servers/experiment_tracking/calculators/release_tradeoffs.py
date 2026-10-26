"""Model-Release Metric Delta & Run-to-Run Variance Calculator (`experiment_tracking/calculators/release_tradeoffs.py`).

Per Phase 6 User Answer 3:
- Computes absolute deltas, percentage changes, and run-to-run sample standard deviation
  between baseline and candidate model versions.
- Never claims statistical significance unless `len(baseline_runs) >= min_runs_for_significance`
  and `len(candidate_runs) >= min_runs_for_significance` (default 5); otherwise explicitly states
  `"not enough runs to assess statistical significance"`.
"""

from __future__ import annotations

from collections.abc import Sequence
import math

from alba_one.mcp_servers.calculators_base import (
    LEGAL_DISCLAIMER_EN,
    CalcResult,
    ScenarioBound,
)


def _mean_and_std(values: Sequence[float]) -> tuple[float, float]:
    n = len(values)
    mean_v = sum(values) / n
    if n < 2:
        return mean_v, 0.0
    var = sum((x - mean_v) ** 2 for x in values) / (n - 1)
    return mean_v, math.sqrt(var)


def calculate_model_release_tradeoffs(
    *,
    metric_name: str,
    unit: str,
    baseline_runs: Sequence[float],
    candidate_runs: Sequence[float],
    min_runs_for_significance: int = 5,
    data_window: str = "2026-10 evaluation suite",
) -> CalcResult:
    """Compute candidate vs baseline mean delta, percentage change, and run-to-run variance."""
    n_base = len(baseline_runs)
    n_cand = len(candidate_runs)
    inputs = {
        "metric_name": metric_name,
        "baseline_run_count": n_base,
        "candidate_run_count": n_cand,
        "min_runs_for_significance": min_runs_for_significance,
    }
    if n_base == 0 or n_cand == 0:
        return CalcResult(
            formula_id="experiment.model_release_delta",
            version="1.0.0",
            status="insufficient_data",
            value=None,
            unit=unit,
            method="Difference of means across evaluation runs",
            inputs=inputs,
            assumptions=["At least 1 run per model version is required to compute a mean delta."],
            data_window=data_window,
            sample_size=min(n_base, n_cand),
            warnings=["Insufficient data: baseline_runs or candidate_runs is empty."],
            disclaimer=LEGAL_DISCLAIMER_EN,
        )

    base_mean, base_std = _mean_and_std(baseline_runs)
    cand_mean, cand_std = _mean_and_std(candidate_runs)
    abs_delta = round(cand_mean - base_mean, 4)
    pct_change = round(((cand_mean - base_mean) / base_mean) * 100.0, 2) if base_mean != 0 else 0.0

    # Worst/base/best observed difference across run extremes
    low_delta = round(min(candidate_runs) - max(baseline_runs), 4)
    high_delta = round(max(candidate_runs) - min(baseline_runs), 4)

    warnings: list[str] = []
    if n_base < min_runs_for_significance or n_cand < min_runs_for_significance:
        sig_note = (
            f"not enough runs to assess statistical significance "
            f"(baseline={n_base}, candidate={n_cand}, required>={min_runs_for_significance})"
        )
        warnings.append(sig_note)
    else:
        sig_note = f"sample size sufficient (baseline={n_base}, candidate={n_cand}) for two-sample comparison"

    scenarios = [
        ScenarioBound("low", "min(candidate) - max(baseline)", low_delta, unit),
        ScenarioBound("base", f"mean_delta (pct_change={pct_change:+.2f}%)", abs_delta, unit),
        ScenarioBound("high", "max(candidate) - min(baseline)", high_delta, unit),
    ]
    return CalcResult(
        formula_id="experiment.model_release_delta",
        version="1.0.0",
        status="ok",
        value=abs_delta,
        unit=unit,
        method=(
            f"candidate_mean ({cand_mean:.4f}, std={cand_std:.4f}) - "
            f"baseline_mean ({base_mean:.4f}, std={base_std:.4f}); "
            f"pct_change={pct_change:+.2f}%; {sig_note}"
        ),
        inputs={
            **inputs,
            "baseline_mean": round(base_mean, 4),
            "baseline_std": round(base_std, 4),
            "candidate_mean": round(cand_mean, 4),
            "candidate_std": round(cand_std, 4),
            "pct_change": pct_change,
        },
        assumptions=[
            "Both model versions were evaluated on the identical golden dataset split and judge model.",
            sig_note,
        ],
        scenarios=scenarios,
        data_window=data_window,
        sample_size=min(n_base, n_cand),
        uncertainty_range=(low_delta, high_delta),
        warnings=warnings,
        disclaimer=LEGAL_DISCLAIMER_EN,
    )
