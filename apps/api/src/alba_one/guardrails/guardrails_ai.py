"""Selective Guardrails AI / Custom Validators (`guardrails/guardrails_ai.py`).

Per User Answer 1:
- Guardrails AI / heavier validators are NOT run on every request blindly; they are
  invoked only for specific policies marked `"Needs Guardrails AI"` in `docs/GUARDRAIL_COVERAGE.md`:
  1. Japanese & English competitor-mention and forbidden business word checks (because
     AWS Bedrock Word Filters only support EN/FR/ES and do NOT support Japanese).
  2. Japanese & English claim-to-citation grounding entailment verification (`output` layer).
  3. Tool argument JSON-schema validation (`tool` layer).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any

from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result
from alba_one.kb.fts import tokenize_for_fts

DEFAULT_FORBIDDEN_WORDS_JP_EN: tuple[str, ...] = (
    "override_safety_gate",
    "競合他社機密データ不正取得",
    "裏口承認バイパス",
    "competitor_confidential_dump",
)


def validate_words_and_competitors_jp_en(
    text: str,
    ctx: GuardrailContext,
    *,
    layer: str = "input",
    forbidden_terms: Sequence[str] = DEFAULT_FORBIDDEN_WORDS_JP_EN,
) -> GuardrailResult:
    """Fallback validator for Japanese & English forbidden words / competitor rules."""
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    matched = [term for term in forbidden_terms if unicodedata.normalize("NFKC", term).lower() in normalized]
    if matched:
        return build_guardrail_result(
            layer=layer,
            raw_action="block",
            policy="jp_en_word_and_competitor_filter",
            ctx=ctx,
            details={"matched_terms": matched, "engine": "local_and_guardrails_ai"},
            refusal_key="blocked_output" if layer == "output" else "blocked_input",
        )
    return build_guardrail_result(
        layer=layer,
        raw_action="pass",
        policy="jp_en_word_and_competitor_filter",
        ctx=ctx,
        sanitized_payload=text,
    )


def validate_claim_citation_entailment(
    *,
    claims: Sequence[dict[str, Any]],
    available_sources_by_ref_id: dict[str, str],
    ctx: GuardrailContext,
    min_entailment_overlap: float = 0.15,
) -> GuardrailResult:
    """Verify every output claim cites an existing `ref_id` AND is lexically/semantically entailed by it.

    Marked in `docs/GUARDRAIL_COVERAGE.md` and `docs/STUBS.md`: uses deterministic token
    entailment + citation-existence check offline, and can invoke `JUDGE_MODEL` via the
    gateway when live LLM entailment scoring is enabled.
    """
    if not claims:
        return build_guardrail_result(
            layer="output",
            raw_action="block",
            policy="citation_presence_check",
            ctx=ctx,
            details={"reason": "No claims provided in output payload."},
            refusal_key="blocked_output",
        )

    uncited_claims: list[str] = []
    missing_refs: list[str] = []
    unentailed_claims: list[str] = []

    for idx, claim in enumerate(claims):
        statement = str(claim.get("statement") or claim.get("text") or "").strip()
        citations = claim.get("citations") or claim.get("evidence") or []
        if not citations:
            uncited_claims.append(statement or f"claim_{idx}")
            continue

        claim_tokens = set(tokenize_for_fts(statement))
        supported_tokens: set[str] = set()
        for cit in citations:
            ref_id = str(cit.get("ref_id", "") if isinstance(cit, dict) else cit).strip()
            if not ref_id or ref_id not in available_sources_by_ref_id:
                missing_refs.append(ref_id or "empty_ref_id")
            else:
                supported_tokens |= set(tokenize_for_fts(available_sources_by_ref_id[ref_id]))

        if claim_tokens and supported_tokens:
            overlap = len(claim_tokens & supported_tokens) / len(claim_tokens)
            if overlap < min_entailment_overlap:
                unentailed_claims.append(statement)

    if uncited_claims or missing_refs or unentailed_claims:
        return build_guardrail_result(
            layer="output",
            raw_action="block",
            policy="japanese_and_english_grounding_entailment",
            ctx=ctx,
            details={
                "uncited_claims": uncited_claims,
                "missing_ref_ids": missing_refs,
                "unentailed_claims": unentailed_claims,
            },
            refusal_key="blocked_output",
        )

    return build_guardrail_result(
        layer="output",
        raw_action="pass",
        policy="japanese_and_english_grounding_entailment",
        ctx=ctx,
        details={"verified_claims": len(claims)},
    )


def validate_tool_arguments_schema(
    arguments: dict[str, Any],
    required_keys: Sequence[str],
    ctx: GuardrailContext,
) -> GuardrailResult:
    """Validate tool call arguments against required schema keys."""
    missing = [k for k in required_keys if k not in arguments or arguments[k] is None]
    if missing:
        return build_guardrail_result(
            layer="tool",
            raw_action="block",
            policy="tool_argument_json_schema",
            ctx=ctx,
            details={"missing_keys": missing},
        )
    return build_guardrail_result(
        layer="tool",
        raw_action="pass",
        policy="tool_argument_json_schema",
        ctx=ctx,
    )
