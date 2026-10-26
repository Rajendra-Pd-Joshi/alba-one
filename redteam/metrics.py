"""Prometheus Exposition Formatter for Red-Team & Safety Metrics (`redteam/metrics.py` — Phase 11).

Exposes all required Phase 11 metrics labelled by `version`, `environment`, and `language`:
- `redteam_critical_bypass_count`
- `redteam_asr` (labelled by `family`, `version`, `environment`, `language`)
- `redteam_false_positive_rate`
- `redteam_run_duration_seconds`
- `redteam_run_cost`
- `redteam_last_run_age_seconds`
- `redteam_scenarios_quarantined`
- `redteam_detection_coverage`
"""

from __future__ import annotations

from typing import Any


def render_prometheus_metrics(
    report: dict[str, Any],
    *,
    app_version: str = "1.0.0",
    environment: str = "staging",
    last_run_age_seconds: float = 0.0,
    quarantined_count: int = 0,
    detection_coverage: float = 1.0,
) -> str:
    """Render Prometheus text-format metrics for Argo Rollouts analysis and alerting."""
    lines: list[str] = [
        "# HELP redteam_critical_bypass_count Number of critical guardrail bypasses observed.",
        "# TYPE redteam_critical_bypass_count gauge",
        f'redteam_critical_bypass_count{{version="{app_version}",environment="{environment}"}} {int(report.get("critical_bypasses", 0))}',
        "# HELP redteam_false_positive_rate Benign prompt false-positive block rate.",
        "# TYPE redteam_false_positive_rate gauge",
        f'redteam_false_positive_rate{{version="{app_version}",environment="{environment}",language="all"}} {float(report.get("benign_false_positive_rate", 0.0)):.6f}',
    ]

    by_lang = report.get("by_language", {})
    for lang, stats in by_lang.items():
        fp_l = float(stats.get("false_positive_rate", report.get("benign_false_positive_rate", 0.0)))
        lines.append(
            f'redteam_false_positive_rate{{version="{app_version}",environment="{environment}",language="{lang}"}} {fp_l:.6f}'
        )

    lines.extend(
        [
            "# HELP redteam_asr Attack success rate per scenario family.",
            "# TYPE redteam_asr gauge",
        ]
    )
    for fam, stats in report.get("by_family", {}).items():
        asr = float(stats.get("asr", 0.0))
        lines.append(
            f'redteam_asr{{version="{app_version}",environment="{environment}",family="{fam}"}} {asr:.6f}'
        )

    lines.extend(
        [
            "# HELP redteam_run_duration_seconds Total duration of the red-team run in seconds.",
            "# TYPE redteam_run_duration_seconds gauge",
            f'redteam_run_duration_seconds{{version="{app_version}",environment="{environment}"}} {float(report.get("duration_seconds", 0.0)):.3f}',
            "# HELP redteam_run_cost Total cost of the red-team run in USD.",
            "# TYPE redteam_run_cost gauge",
            f'redteam_run_cost{{version="{app_version}",environment="{environment}"}} {float(report.get("measured_cost_usd", 0.0)):.6f}',
            "# HELP redteam_last_run_age_seconds Seconds since the last completed red-team run (dead-man switch).",
            "# TYPE redteam_last_run_age_seconds gauge",
            f'redteam_last_run_age_seconds{{version="{app_version}",environment="{environment}"}} {float(last_run_age_seconds):.1f}',
            "# HELP redteam_scenarios_quarantined Count of currently quarantined flaky scenarios.",
            "# TYPE redteam_scenarios_quarantined gauge",
            f'redteam_scenarios_quarantined{{version="{app_version}",environment="{environment}"}} {int(quarantined_count)}',
            "# HELP redteam_detection_coverage Fraction of expected blocking layers that fired on attack scenarios.",
            "# TYPE redteam_detection_coverage gauge",
            f'redteam_detection_coverage{{version="{app_version}",environment="{environment}"}} {float(detection_coverage):.6f}',
        ]
    )
    return "\n".join(lines) + "\n"
