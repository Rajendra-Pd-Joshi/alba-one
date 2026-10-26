"""Outbound Query Guardrail for External MCP Tools (`guardrails/outbound_query.py`).

Mandatory pre-egress check for every tool classed `external`:
1. Redacts PII (`PIIRedactor`) and blocks leaked secrets/canaries (`scan_for_secrets`).
2. Checks the outbound query against a per-tenant `sensitive_terms` dictionary
   (fictional project code names, fictional customer names, unreleased product names,
   internal metric names).
3. Enforces `OUTBOUND_QUERY_POLICY`:
   - `"block"` (default in `production`): blocks the external tool call if any sensitive term is found.
   - `"generalize"` (default in `development` / `test`): replaces each sensitive term with its
     generic public description and returns `action="mask"`.
4. Logs a `GuardrailEventRecord` with the action and category count, **NEVER logging
   the matched sensitive term itself** in event details or logs.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result
from alba_one.kb.pii import PIIRedactor

OutboundQueryPolicyType = Literal["block", "generalize"]

_CANARY_TOKEN_RE = re.compile(r"CANARY-[0-9A-Fa-f]{6,32}")

# Clearly fictional markers per Phase 9 User Answer 2 ("Test data hygiene")
_SHARED_FICTIONAL_TERMS: dict[str, dict[str, str]] = {
    "FICTIONAL-CODE-KAGUYA-架空": {
        "category": "internal_project_codename",
        "ja": "次世代港湾自動化システム",
        "en": "automated port terminal logistics system",
    },
    "PROJECT-KAGUYA": {
        "category": "internal_project_codename",
        "ja": "次世代港湾自動化システム",
        "en": "automated port terminal logistics system",
    },
    "プロジェクトかぐや": {
        "category": "internal_project_codename",
        "ja": "次世代港湾自動化システム",
        "en": "automated port terminal logistics system",
    },
    "架空テスト海運株式会社": {
        "category": "customer_name",
        "ja": "国内大手海運事業者",
        "en": "major domestic shipping operator",
    },
    "Fictional Test Maritime Corp": {
        "category": "customer_name",
        "ja": "国内大手海運事業者",
        "en": "major domestic shipping operator",
    },
    "東都製薬株式会社": {
        "category": "customer_name",
        "ja": "国内大手製薬メーカー",
        "en": "major Japanese pharmaceutical manufacturer",
    },
    "Toto Pharma Corp": {
        "category": "customer_name",
        "ja": "国内大手製薬メーカー",
        "en": "major Japanese pharmaceutical manufacturer",
    },
    "ALBA-NEPTUNE-V3-UNRELEASED": {
        "category": "unreleased_product_name",
        "ja": "海運ETA予測AIモデル",
        "en": "maritime ETA forecasting AI model",
    },
    "internal_berth_margin_alpha": {
        "category": "internal_metric_name",
        "ja": "港湾バース稼働効率指標",
        "en": "port berth utilization efficiency metric",
    },
}

DEFAULT_TENANT_SENSITIVE_TERMS: dict[str, dict[str, dict[str, str]]] = {
    "tenant_alba_demo": _SHARED_FICTIONAL_TERMS,
    "tenant_fictional_alpha": _SHARED_FICTIONAL_TERMS,
}


def check_outbound_query(
    query: str,
    ctx: GuardrailContext,
    *,
    policy_mode: OutboundQueryPolicyType = "generalize",
    tenant_sensitive_terms: dict[str, dict[str, str]] | None = None,
    redactor: PIIRedactor | None = None,
) -> GuardrailResult:
    """Inspect and sanitize an outbound external search query before network egress.

    IMPORTANT: Never includes the raw sensitive term or canary in `details` or `GuardrailEventRecord`.
    """
    if not query or not query.strip():
        return build_guardrail_result(
            layer="tool",
            raw_action="block",
            policy="outbound_query_empty",
            ctx=ctx,
            details={"reason": "Empty outbound query"},
        )

    # 1. Block leaked credentials/secrets or planted CANARY-<hex> tokens unconditionally
    leaked_secrets = scan_for_secrets(query)
    if leaked_secrets or _CANARY_TOKEN_RE.search(query):
        return build_guardrail_result(
            layer="tool",
            raw_action="block",
            policy="outbound_query_secret_blocked",
            ctx=ctx,
            details={"secret_categories": leaked_secrets or ["canary_token"]},
        )

    # 2. Redact PII before any external provider sees the query
    pii_res = (redactor or PIIRedactor()).redact(query)
    working_query = pii_res.redacted_text

    # 3. Check per-tenant sensitive terms (case-insensitive & NFKC normalized)
    terms_map = (
        tenant_sensitive_terms
        if tenant_sensitive_terms is not None
        else DEFAULT_TENANT_SENSITIVE_TERMS.get(ctx.tenant_id, _SHARED_FICTIONAL_TERMS)
    )
    matched_categories: list[str] = []
    norm_working = unicodedata.normalize("NFKC", working_query)

    for raw_term, spec in terms_map.items():
        norm_term = unicodedata.normalize("NFKC", raw_term)
        pattern = re.compile(re.escape(norm_term), re.IGNORECASE)
        if pattern.search(norm_working):
            matched_categories.append(spec.get("category", "sensitive_term"))
            replacement = spec.get("ja" if ctx.lang == "ja" else "en", "public industry concept")
            norm_working = pattern.sub(replacement, norm_working)

    if matched_categories:
        safe_details: dict[str, Any] = {
            "outbound_query_policy": policy_mode,
            "sensitive_term_count": len(matched_categories),
            "matched_categories": sorted(set(matched_categories)),
            "pii_redacted_count": pii_res.total_redactions,
        }
        if policy_mode == "block":
            return build_guardrail_result(
                layer="tool",
                raw_action="block",
                policy="outbound_query_sensitive_term_blocked",
                ctx=ctx,
                details=safe_details,
                refusal_key="blocked_input",
            )
        return build_guardrail_result(
            layer="tool",
            raw_action="mask",
            policy="outbound_query_sensitive_term_generalized",
            ctx=ctx,
            details=safe_details,
            sanitized_payload=norm_working,
        )

    if pii_res.contains_pii:
        return build_guardrail_result(
            layer="tool",
            raw_action="mask",
            policy="outbound_query_pii_redacted",
            ctx=ctx,
            details={"pii_counts": pii_res.counts},
            sanitized_payload=norm_working,
        )

    return build_guardrail_result(
        layer="tool",
        raw_action="pass",
        policy="outbound_query_clean",
        ctx=ctx,
        sanitized_payload=norm_working,
    )
