"""Deterministic Citation, Numeric-Grounding & Confidence Validator (`agents/hypothesis/validator.py`).

Per Phase 6 User Answer 2 & Phase 7 User Answer 3:
- Deterministic checks (a)-(f) for citations and numeric claims.
- Documented anti-contamination rule in `compute_hypothesis_confidence`:
  A `past_decision_lesson` from a single outcome (`evidence_grade == "single_outcome"`)
  must NEVER by itself raise a hypothesis's confidence (`lesson_boost = 0.0`).
  Minimum corroboration threshold (`MIN_EVIDENCE_FOR_STRONG_LESSON`) is `TODO(owner)`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Literal
import unicodedata

from alba_one.agents.hypothesis.ledger import EvidenceLedger, EvidenceLedgerItem

StanceType = Literal["support", "oppose", "neutral"]


@dataclass(frozen=True)
class LLMCitationDraft:
    """Raw citation emitted by the LLM (contains ONLY `evidence_id` + `quote` or `locator`)."""

    evidence_id: str
    quote: str | None = None
    locator: str | None = None


@dataclass(frozen=True)
class ResolvedEvidenceCitation:
    """Fully grounded citation populated by ALBA ONE code from the `EvidenceLedger`."""

    evidence_id: str
    source_type: str
    source_id: str
    url: str | None
    retrieved_at: str
    external: bool
    quote: str | None = None
    locator: str | None = None
    resolved_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMHypothesisDraft:
    """Unvalidated hypothesis draft returned by the LLM before deterministic verification."""

    hypothesis_id: str
    option_label: str
    is_baseline: bool
    statement: str
    stance: StanceType
    rationale: str
    assumptions: list[str]
    risks: list[str]
    what_would_change_my_mind: str
    citations: list[LLMCitationDraft]
    acknowledged_gaps: list[str] = field(default_factory=list)
    depends_on_external: bool = False


@dataclass(frozen=True)
class ValidatedHypothesis:
    """Verified hypothesis with code-populated `ResolvedEvidenceCitation` records."""

    hypothesis_id: str
    option_label: str
    is_baseline: bool
    statement: str
    stance: StanceType
    rationale: str
    assumptions: list[str]
    risks: list[str]
    what_would_change_my_mind: str
    citations: list[ResolvedEvidenceCitation]
    acknowledged_gaps: list[str] = field(default_factory=list)
    depends_on_external: bool = False
    confidence_score: float = 0.80

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HypothesisValidationIssue:
    """Single deterministic validation error for repair feedback or `validation_report`."""

    hypothesis_id: str
    code: str
    message: str
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_for_quote_match(text: str) -> str:
    norm = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", norm).strip()


def resolve_locator(data: Any, locator: str) -> tuple[bool, Any]:
    if not locator or not locator.strip():
        return False, None
    current: Any = data
    for raw_part in locator.strip().split("."):
        part = raw_part.strip()
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit():
                matched = next(
                    (it for it in current if isinstance(it, dict) and str(it.get("scenario")) == part),
                    None,
                )
                if matched is None:
                    return False, None
                current = matched
            else:
                idx = int(part)
                if idx < 0 or idx >= len(current):
                    return False, None
                current = current[idx]
        else:
            return False, None
    return True, current


_IDENTIFIER_NOISE_RE = re.compile(
    r"(?:[HVBR]\d+(?:\.\d+)?|v\d+(?:\.\d+)+|第\d+条|Article\s+\d+|2\s*[-〜~]\s*8\s*[℃C]|p95|p99|36協定)",
    re.IGNORECASE,
)
_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:,\d{3})*(?:\.\d+)?")


def extract_heuristic_numbers(text: str) -> list[float]:
    norm = unicodedata.normalize("NFKC", text)
    cleaned = _IDENTIFIER_NOISE_RE.sub(" ", norm)
    out: list[float] = []
    for match in _NUMBER_TOKEN_RE.findall(cleaned):
        try:
            out.append(float(match.replace(",", "").lstrip("+")))
        except ValueError:
            continue
    return out


def _number_appears_in_item(num: float, item: EvidenceLedgerItem) -> bool:
    for c in extract_heuristic_numbers(item.raw_text):
        if abs(c - num) <= 1e-4 or abs(abs(c) - abs(num)) <= 1e-4:
            return True
    return False


def compute_hypothesis_confidence(
    cited_items: list[EvidenceLedgerItem],
    *,
    min_evidence_for_strong_lesson: int = 3,  # TODO(owner): calibrate corroboration threshold
) -> float:
    """Compute hypothesis confidence while enforcing the Phase 7 anti-contamination rule.

    Rule: A `past_decision_lesson` from a single outcome (`evidence_grade == 'single_outcome'`)
    must NEVER by itself raise a hypothesis's confidence (`lesson_boost = 0.0`).
    """
    primary_count = sum(1 for it in cited_items if it.source_type != "past_decision_lesson")
    corroborated_lessons = sum(
        1
        for it in cited_items
        if it.source_type == "past_decision_lesson"
        and it.structured_data.get("evidence_grade") == "corroborated"
        and int(it.structured_data.get("corroborated_count", 1)) >= min_evidence_for_strong_lesson
    )
    if primary_count == 0 and corroborated_lessons == 0:
        return 0.45  # Single-outcome lesson only -> never raises confidence above baseline
    base = 0.72 + min(0.20, 0.06 * primary_count) + min(0.06, 0.03 * corroborated_lessons)
    return round(min(0.95, base), 4)


def validate_single_hypothesis(
    draft: LLMHypothesisDraft,
    ledger: EvidenceLedger,
    *,
    run_tenant_id: str,
) -> tuple[ValidatedHypothesis | None, list[HypothesisValidationIssue]]:
    """Run all deterministic checks (a)-(f) on a single `LLMHypothesisDraft`."""
    issues: list[HypothesisValidationIssue] = []
    if not draft.citations:
        issues.append(HypothesisValidationIssue(draft.hypothesis_id, "missing_citations", "Hypothesis requires >=1 citation."))
        return None, issues

    resolved_citations: list[ResolvedEvidenceCitation] = []
    cited_items: list[EvidenceLedgerItem] = []

    for cit in draft.citations:
        item = ledger.get(cit.evidence_id)
        if item is None:
            issues.append(HypothesisValidationIssue(draft.hypothesis_id, "forged_evidence_id", f"'{cit.evidence_id}' not in ledger.", cit.evidence_id))
            continue
        if item.tenant_id != run_tenant_id:
            issues.append(HypothesisValidationIssue(draft.hypothesis_id, "cross_tenant_evidence", f"'{cit.evidence_id}' belongs to '{item.tenant_id}'.", cit.evidence_id))
            continue
        if not cit.quote and not cit.locator:
            issues.append(HypothesisValidationIssue(draft.hypothesis_id, "empty_quote_and_locator", f"Citation '{cit.evidence_id}' needs quote or locator.", cit.evidence_id))
            continue

        resolved_val: Any = None
        if cit.quote:
            norm_q = normalize_for_quote_match(cit.quote)
            if not norm_q or norm_q not in normalize_for_quote_match(item.raw_text):
                issues.append(HypothesisValidationIssue(draft.hypothesis_id, "quote_not_found_in_evidence", f"Quote not found in '{cit.evidence_id}'.", cit.evidence_id))
                continue
        if cit.locator:
            ok, resolved_val = resolve_locator(item.structured_data, cit.locator)
            if not ok:
                issues.append(HypothesisValidationIssue(draft.hypothesis_id, "locator_not_found_in_structured_data", f"Locator '{cit.locator}' missing in '{cit.evidence_id}'.", cit.evidence_id))
                continue

        cited_items.append(item)
        resolved_citations.append(
            ResolvedEvidenceCitation(
                evidence_id=item.evidence_id,
                source_type=item.source_type,
                source_id=item.source_id,
                url=item.url,
                retrieved_at=item.retrieved_at,
                external=item.external,
                quote=cit.quote,
                locator=cit.locator,
                resolved_value=resolved_val,
            )
        )

    if draft.depends_on_external and not any(it.external for it in cited_items):
        issues.append(HypothesisValidationIssue(draft.hypothesis_id, "missing_external_citation", "depends_on_external=True requires >=1 external citation."))

    for num in extract_heuristic_numbers(f"{draft.statement} {draft.rationale}"):
        if not any(_number_appears_in_item(num, it) for it in cited_items):
            issues.append(HypothesisValidationIssue(draft.hypothesis_id, "ungrounded_number_in_hypothesis", f"Number '{num}' not found in cited evidence."))

    if issues:
        return None, issues

    conf = compute_hypothesis_confidence(cited_items)
    return (
        ValidatedHypothesis(
            hypothesis_id=draft.hypothesis_id,
            option_label=draft.option_label,
            is_baseline=draft.is_baseline,
            statement=draft.statement,
            stance=draft.stance,
            rationale=draft.rationale,
            assumptions=list(draft.assumptions),
            risks=list(draft.risks),
            what_would_change_my_mind=draft.what_would_change_my_mind,
            citations=resolved_citations,
            acknowledged_gaps=list(draft.acknowledged_gaps),
            depends_on_external=draft.depends_on_external,
            confidence_score=conf,
        ),
        [],
    )
