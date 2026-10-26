"""Deterministic Option Comparison Table Builder (`agents/judge/comparison.py`).

Per Phase 7 User Answer 1:
- Criteria live in `config/decision_criteria/<workflow>.yaml`.
- `build_comparison_table` is a pure function:
  - Rows = every validated hypothesis-backed option plus `H_BASELINE`.
  - Columns = criteria from config.
  - Numeric cells come ONLY from `CalcResult` or tool results in the `EvidenceLedger`,
    carrying `evidence_id`.
  - Qualitative cells (e.g. `reversibility`) are filled by a separate validated step,
    and each must cite a valid ledger `evidence_id` or say `"no_evidence"`.
  - Missing data stays visibly `"missing"`; never fill gaps.
  - No composite score by default (`weighted_totals=None`) unless `weights_reviewed_by`
    is set to a non-empty, non-`TODO` reviewer string.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.validator import ValidatedHypothesis, resolve_locator
from alba_one.kb.indexer import find_repo_root

CellStatusType = Literal["ok", "parameters_not_verified", "insufficient_data", "missing", "no_evidence"]


@dataclass(frozen=True)
class CriterionSpec:
    """Single criterion loaded from `config/decision_criteria/<workflow>.yaml`."""

    id: str
    name_ja: str
    name_en: str
    unit: str
    direction: Literal["higher_better", "lower_better", "n/a"]
    kind: Literal["hard_constraint", "soft_criterion"]
    required: bool
    source_id: str
    locator: str
    hard_limit: float | None = None
    is_regulatory_or_safety: bool = False
    weight: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ComparisonCell:
    """Single cell `(option_id, criterion_id)` in a `ComparisonTable`."""

    criterion_id: str
    status: CellStatusType
    value: Any
    unit: str
    evidence_id: str | None = None
    hard_constraint_passed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionComparisonRow:
    """One option row (`H1..Hn` or `H_BASELINE`) across all workflow criteria."""

    hypothesis_id: str
    option_label: str
    is_baseline: bool
    cells: dict[str, ComparisonCell]
    all_hard_constraints_passed: bool
    has_violated_hard_constraint: bool
    weighted_total: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "option_label": self.option_label,
            "is_baseline": self.is_baseline,
            "cells": {k: v.to_dict() for k, v in self.cells.items()},
            "all_hard_constraints_passed": self.all_hard_constraints_passed,
            "has_violated_hard_constraint": self.has_violated_hard_constraint,
            "weighted_total": self.weighted_total,
        }


@dataclass(frozen=True)
class ComparisonTable:
    """Complete deterministic option comparison matrix."""

    workflow: str
    criteria: list[CriterionSpec]
    rows: list[OptionComparisonRow]
    weights_reviewed_by: str
    weighted_score_status: Literal["weights_not_reviewed", "reviewed"]
    tradeoffs_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "criteria": [c.to_dict() for c in self.criteria],
            "rows": [r.to_dict() for r in self.rows],
            "weights_reviewed_by": self.weights_reviewed_by,
            "weighted_score_status": self.weighted_score_status,
            "tradeoffs_summary": self.tradeoffs_summary,
        }


def load_decision_criteria(
    workflow: str = "default",
    *,
    config_dir: str | Path | None = None,
    weights_reviewed_by_override: str | None = None,
) -> tuple[str, list[CriterionSpec]]:
    """Load `config/decision_criteria/<workflow>.yaml` (falling back to `default.yaml`)."""
    base = Path(config_dir) if config_dir else (find_repo_root() / "config" / "decision_criteria")
    path = base / f"{workflow}.yaml"
    if not path.is_file():
        path = base / "default.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    reviewed_by = (
        weights_reviewed_by_override
        if weights_reviewed_by_override is not None
        else str(raw.get("weights_reviewed_by", "TODO(owner)"))
    )
    specs: list[CriterionSpec] = []
    for item in raw.get("criteria", []):
        src = item.get("source", {})
        specs.append(
            CriterionSpec(
                id=str(item["id"]),
                name_ja=str(item["name_ja"]),
                name_en=str(item["name_en"]),
                unit=str(item["unit"]),
                direction=item["direction"],
                kind=item["kind"],
                required=bool(item.get("required", True)),
                source_id=str(src.get("source_id", "")),
                locator=str(src.get("locator", "value")),
                hard_limit=float(item["hard_limit"]) if item.get("hard_limit") is not None else None,
                is_regulatory_or_safety=bool(item.get("is_regulatory_or_safety", False)),
                weight=float(item["weight"]) if item.get("weight") is not None else None,
            )
        )
    return reviewed_by, specs


def _evaluate_hard_limit(val: Any, spec: CriterionSpec) -> bool | None:
    if spec.kind != "hard_constraint" or spec.hard_limit is None or val is None:
        return None
    num_val = 1.0 if val is True else (0.0 if val is False else float(val))
    if spec.direction == "lower_better":
        return num_val <= spec.hard_limit
    if spec.direction == "higher_better":
        return num_val >= spec.hard_limit
    return None


def build_comparison_table(
    hypotheses: list[ValidatedHypothesis],
    ledger: EvidenceLedger,
    criteria: list[CriterionSpec],
    *,
    workflow: str = "default",
    weights_reviewed_by: str = "TODO(owner)",
    qualitative_cells: dict[tuple[str, str], dict[str, str]] | None = None,
) -> ComparisonTable:
    """Pure function building `ComparisonTable` strictly from `EvidenceLedger` items."""
    weights_are_reviewed = bool(
        weights_reviewed_by.strip() and not weights_reviewed_by.strip().upper().startswith("TODO")
    )
    qual_map = qualitative_cells or {}
    ledger_by_source = {it.source_id: it for it in ledger.items()}

    rows: list[OptionComparisonRow] = []
    for hyp in hypotheses:
        row_cells: dict[str, ComparisonCell] = {}
        hard_violated = False
        all_hard_ok = True

        for c_spec in criteria:
            if c_spec.unit == "qualitative" or c_spec.source_id == "qualitative":
                q_entry = qual_map.get((hyp.hypothesis_id, c_spec.id))
                if q_entry and q_entry.get("evidence_id") and ledger.get(q_entry["evidence_id"]) is not None:
                    row_cells[c_spec.id] = ComparisonCell(
                        criterion_id=c_spec.id,
                        status="ok",
                        value=q_entry.get("text", "documented"),
                        unit="qualitative",
                        evidence_id=q_entry["evidence_id"],
                    )
                else:
                    row_cells[c_spec.id] = ComparisonCell(
                        criterion_id=c_spec.id,
                        status="no_evidence",
                        value="no_evidence",
                        unit="qualitative",
                        evidence_id=None,
                    )
                continue

            item = ledger_by_source.get(c_spec.source_id)
            if item is None:
                row_cells[c_spec.id] = ComparisonCell(
                    criterion_id=c_spec.id,
                    status="missing",
                    value=None,
                    unit=c_spec.unit,
                )
                if c_spec.kind == "hard_constraint" and c_spec.required:
                    all_hard_ok = False
                continue

            calc_status = item.structured_data.get("status")
            if calc_status in ("parameters_not_verified", "insufficient_data"):
                row_cells[c_spec.id] = ComparisonCell(
                    criterion_id=c_spec.id,
                    status=calc_status,
                    value=None,
                    unit=c_spec.unit,
                    evidence_id=item.evidence_id,
                    hard_constraint_passed=None,
                )
                if c_spec.kind == "hard_constraint" and c_spec.required:
                    all_hard_ok = False
                continue

            ok, val = resolve_locator(item.structured_data, c_spec.locator)
            if not ok or val is None:
                row_cells[c_spec.id] = ComparisonCell(
                    criterion_id=c_spec.id,
                    status="missing",
                    value=None,
                    unit=c_spec.unit,
                    evidence_id=item.evidence_id,
                )
                if c_spec.kind == "hard_constraint" and c_spec.required:
                    all_hard_ok = False
                continue

            passed = _evaluate_hard_limit(val, c_spec)
            if passed is False:
                hard_violated = True
                all_hard_ok = False
            row_cells[c_spec.id] = ComparisonCell(
                criterion_id=c_spec.id,
                status="ok",
                value=val,
                unit=c_spec.unit,
                evidence_id=item.evidence_id,
                hard_constraint_passed=passed,
            )

        weighted_val: float | None = None
        if weights_are_reviewed:
            acc = 0.0
            has_any = False
            for c_spec in criteria:
                cell = row_cells[c_spec.id]
                if c_spec.weight and isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                    sign = -1.0 if c_spec.direction == "lower_better" else 1.0
                    acc += sign * float(c_spec.weight) * float(cell.value)
                    has_any = True
            weighted_val = round(acc, 4) if has_any else None

        rows.append(
            OptionComparisonRow(
                hypothesis_id=hyp.hypothesis_id,
                option_label=hyp.option_label,
                is_baseline=hyp.is_baseline,
                cells=row_cells,
                all_hard_constraints_passed=all_hard_ok,
                has_violated_hard_constraint=hard_violated,
                weighted_total=weighted_val,
            )
        )

    return ComparisonTable(
        workflow=workflow,
        criteria=criteria,
        rows=rows,
        weights_reviewed_by=weights_reviewed_by,
        weighted_score_status="reviewed" if weights_are_reviewed else "weights_not_reviewed",
        tradeoffs_summary=[
            f"{r.hypothesis_id} ({r.option_label}): hard_constraints_ok={r.all_hard_constraints_passed}"
            for r in rows
        ],
    )
