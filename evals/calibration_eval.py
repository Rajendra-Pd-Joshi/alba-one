"""Phase 7 Decision Calibration Evaluation (`evals/calibration_eval.py`).

Per Phase 7 User Answer 3:
- Computes calibration / Brier score and confirmation rate from reviewed outcomes.
- Enforces `MIN_OUTCOMES_FOR_STATS` (default 10, `TODO(owner)`): returns `status="insufficient_data"`
  (`"not enough data"`) when sample size is below threshold unless `--synthetic-demo` is passed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def compute_calibration_report(
    samples: list[tuple[float, int]],
    *,
    min_outcomes_for_stats: int = 10,
) -> dict[str, Any]:
    """Compute Brier score and empirical confirmation rate gated on `min_outcomes_for_stats`."""
    n = len(samples)
    if n < min_outcomes_for_stats:
        return {
            "suite": "calibration_eval",
            "status": "insufficient_data",
            "message": "not enough data",
            "sample_size": n,
            "min_outcomes_for_stats": min_outcomes_for_stats,
            "metrics": None,
        }
    brier = sum((conf - outcome) ** 2 for conf, outcome in samples) / n
    confirmed_rate = sum(outcome for _, outcome in samples) / n
    mean_confidence = sum(conf for conf, _ in samples) / n
    return {
        "suite": "calibration_eval",
        "status": "ok",
        "sample_size": n,
        "min_outcomes_for_stats": min_outcomes_for_stats,
        "metrics": {
            "brier_score": round(brier, 4),
            "mean_confidence": round(mean_confidence, 4),
            "empirical_confirmed_rate": round(confirmed_rate, 4),
            "calibration_gap": round(abs(mean_confidence - confirmed_rate), 4),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 7 Calibration Evaluation")
    parser.add_argument("--min-outcomes", type=int, default=10)
    parser.add_argument("--synthetic-demo", action="store_true", help="Run with 12 synthetic reviewed outcomes")
    args = parser.parse_args(argv)

    samples = [(0.84, 1), (0.80, 1), (0.78, 1), (0.82, 0), (0.85, 1), (0.76, 1), (0.88, 1), (0.74, 0), (0.81, 1), (0.83, 1), (0.79, 1), (0.86, 1)] if args.synthetic_demo else []
    print(json.dumps(compute_calibration_report(samples, min_outcomes_for_stats=args.min_outcomes), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
