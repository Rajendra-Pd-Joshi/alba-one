"""Pure data models and deterministic comparison helpers for Outcomes & Write-Back (`agents/outcomes/models.py`)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

HypothesisOutcomeLabel = Literal["confirmed", "refuted", "inconclusive"]
LessonType = Literal[
    "hypothesis_confirmed",
    "hypothesis_refuted",
    "constraint_discovered",
    "process_improvement",
]


@dataclass(frozen=True)
class ActualVsPredictedDelta:
    """Deterministic comparison of an actual KPI value against a stored `CalcResult`."""

    metric_id: str
    actual_value: float
    predicted_base: float
    predicted_low: float
    predicted_high: float
    delta_from_base: float
    pct_delta_from_base: float
    within_low_high_range: bool
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProposedLessonDraft:
    """Draft lesson created upon outcome review and awaiting `knowledge_steward` approval."""

    lesson_id: str
    outcome_id: str
    decision_id: str
    tenant_id: str
    topic_key: str
    lesson_type: LessonType
    statement_ja: str
    statement_en: str
    source_acl_tags: list[str]
    primary_outcome_label: HypothesisOutcomeLabel
    reviewer_id: str
    status: Literal["pending_steward_review", "active", "superseded", "rejected"] = "pending_steward_review"
    evidence_grade: Literal["single_outcome", "corroborated"] = "single_outcome"
    corroborated_count: int = 1
    superseded_by: str | None = None
    approved_by_steward_id: str | None = None
    valid_from: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_actual_vs_predicted(
    *,
    metric_id: str,
    actual_value: float,
    calc_result_dict: dict[str, Any],
) -> ActualVsPredictedDelta:
    """Pure-Python comparison of `actual_value` against a stored `CalcResult` (`low`/`base`/`high`)."""
    base_val = float(calc_result_dict.get("value") or 0.0)
    scenarios = calc_result_dict.get("scenarios") or []
    scen_map = {str(s["scenario"]): float(s["value"]) for s in scenarios if isinstance(s, dict) and "value" in s}
    low_v = min(scen_map.get("low", base_val), scen_map.get("high", base_val), base_val)
    high_v = max(scen_map.get("low", base_val), scen_map.get("high", base_val), base_val)
    delta = round(actual_value - base_val, 4)
    pct = round(((actual_value - base_val) / abs(base_val)) * 100.0, 2) if base_val != 0 else 0.0
    within = low_v <= actual_value <= high_v
    return ActualVsPredictedDelta(
        metric_id=metric_id,
        actual_value=actual_value,
        predicted_base=base_val,
        predicted_low=low_v,
        predicted_high=high_v,
        delta_from_base=delta,
        pct_delta_from_base=pct,
        within_low_high_range=within,
        unit=str(calc_result_dict.get("unit", "")),
    )


def intersect_most_restrictive_acl_tags(acl_lists: list[list[str]]) -> list[str]:
    """Return the intersection of ACL role lists (most restrictive wins; always preserves `role:admin`)."""
    non_empty = [set(lst) for lst in acl_lists if lst]
    if not non_empty:
        return ["role:approver", "role:admin"]
    common = set.intersection(*non_empty)
    common.add("role:admin")
    return sorted(common)
