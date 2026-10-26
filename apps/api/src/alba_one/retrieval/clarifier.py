"""Stage 1: Clarifier (`retrieval/clarifier.py`).

Checks whether a user's decision query is missing required decision context slots:
- Returns structured `ClarificationResult(is_ambiguous, missing_slots, questions, explicit_assumptions)`.
- Enforces at most `MAX_CLARIFICATION_ROUNDS = 2` and at most `MAX_QUESTIONS_PER_ROUND = 3`.
- After 2 rounds, stops asking and proceeds with `explicit_assumptions` listed back to the user
  in their language (`ja` or `en`).
- Accepts `thread_memory` hooks (from Phase 4 short-term memory) so previously answered
  slots are not asked again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_CLARIFICATION_ROUNDS = 2
MAX_QUESTIONS_PER_ROUND = 3

# Concrete entity/identifier tokens that disambiguate a query
_KNOWN_SPECIFIC_MARKERS: tuple[str, ...] = (
    "rt-knt-101",
    "rt-knt-102",
    "rt-tki-204",
    "vh-reefer-08",
    "vh-dry-14",
    "vh-reefer-19",
    "tyo-oi-b3",
    "tyo-oi-b4",
    "yok-hm-d1",
    "オーロラ",
    "aurora",
    "ホライゾン",
    "horizon",
    "クレスト",
    "crest",
    "stf-401",
    "stf-402",
    "stf-403",
    "v2.3.0",
    "v2.4.0",
    "eta-demand-forecaster",
    "isms",
)


@dataclass(frozen=True)
class ClarificationResult:
    """Structured output of the Clarifier stage."""

    is_ambiguous: bool
    round_number: int
    missing_slots: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    explicit_assumptions: list[str] = field(default_factory=list)
    lang: str = "ja"


def _default_questions_for_slots(missing_slots: list[str], lang: str) -> list[str]:
    """Generate concise, concrete clarifying questions in `ja` or `en` (capped at 3)."""
    bank_ja = {
        "target_entity": "対象の船舶名・配送ルートコード・要員コード・モデル名のどれに関する判断ですか？（例：アルバ・オーロラ号、RT-KNT-101、v2.4.0-rc1）",
        "time_window": "対象となる時間帯やシフトはいつですか？（例：2026年10月25日 06:00着岸便、48時間カナリア期間）",
        "priority_constraint": "最優先する制約条件はどれですか？（例：医薬品4時間SLA遵守、36協定残業45時間上限、p95レイテンシ600ms以下）",
    }
    bank_en = {
        "target_entity": "Which specific vessel, route code, staff ID, or ML model version does this decision concern (e.g., MV ALBA AURORA, RT-KNT-101, v2.4.0-rc1)?",
        "time_window": "What target schedule window or shift applies (e.g., 06:00 JST arrival, 48-hour canary window)?",
        "priority_constraint": "Which constraint takes top priority (e.g., 4.0h pharma cold-chain SLA, 45h Article 36 overtime cap, or 600ms p95 latency SLO)?",
    }
    selected_bank = bank_ja if lang == "ja" else bank_en
    questions = [selected_bank[slot] for slot in missing_slots if slot in selected_bank]
    return questions[:MAX_QUESTIONS_PER_ROUND]


def _default_assumptions(missing_slots: list[str], lang: str) -> list[str]:
    """Build explicit fallback assumptions when max clarification rounds (2) are reached."""
    if lang == "ja":
        return [
            "対象拠点・テナントは東京港大井ふ頭／横浜本牧拠点（tenant_alba_demo）と仮定します。",
            "医薬品コールドチェーンSLA（4.0時間以内）および36協定月間残業上限（45.0時間）を標準制約として適用します。",
            f"未指定の項目（{', '.join(missing_slots)}）は直近の標準運航計画値を前提に評価します。",
        ][:MAX_QUESTIONS_PER_ROUND]
    return [
        "Assuming primary Tokyo Oi Pier / Yokohama Honmoku operations (tenant_alba_demo).",
        "Applying standard 4.0h pharma cold-chain SLA and 45.0h Article 36 monthly overtime cap.",
        f"Evaluating unspecified slots ({', '.join(missing_slots)}) using current baseline schedule defaults.",
    ][:MAX_QUESTIONS_PER_ROUND]


def analyze_clarification(
    query: str,
    *,
    lang: str = "ja",
    round_number: int = 0,
    clarification_answers: list[str] | None = None,
    thread_memory: dict[str, Any] | None = None,
) -> ClarificationResult:
    """Evaluate query ambiguity respecting the 2-round / 3-question cap and thread memory."""
    combined_context = " ".join(
        [
            query.lower(),
            " ".join(a.lower() for a in (clarification_answers or [])),
            str((thread_memory or {}).get("summary", "")).lower(),
        ]
    )

    has_specific_entity = any(marker in combined_context for marker in _KNOWN_SPECIFIC_MARKERS)
    is_short_or_vague = len(query.strip()) < 14 and not has_specific_entity

    missing_slots: list[str] = []
    if not has_specific_entity:
        missing_slots.append("target_entity")
    if is_short_or_vague:
        missing_slots.extend(["time_window", "priority_constraint"])

    # Deduplicate while preserving order and cap at 3
    unique_missing = list(dict.fromkeys(missing_slots))[:MAX_QUESTIONS_PER_ROUND]

    if not unique_missing:
        return ClarificationResult(
            is_ambiguous=False,
            round_number=round_number,
            missing_slots=[],
            questions=[],
            explicit_assumptions=[],
            lang=lang,
        )

    # After 2 rounds of clarification, stop asking and proceed with explicit assumptions
    if round_number >= MAX_CLARIFICATION_ROUNDS:
        return ClarificationResult(
            is_ambiguous=False,
            round_number=round_number,
            missing_slots=unique_missing,
            questions=[],
            explicit_assumptions=_default_assumptions(unique_missing, lang),
            lang=lang,
        )

    questions = _default_questions_for_slots(unique_missing, lang)
    return ClarificationResult(
        is_ambiguous=True,
        round_number=round_number + 1,
        missing_slots=unique_missing,
        questions=questions[:MAX_QUESTIONS_PER_ROUND],
        explicit_assumptions=[],
        lang=lang,
    )
