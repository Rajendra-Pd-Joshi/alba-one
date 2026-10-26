"""Layer 3: Output Guardrail (`guardrails/output_layer.py`).

Runs AWS Bedrock `ApplyGuardrail(source='OUTPUT')` (including contextual grounding)
in parallel (`asyncio.gather`) with local deterministic + Guardrails AI checks:
1. Every claim in the output has at least one citation `ref_id` that exists in the run's
   `available_sources_by_ref_id` and is lexically/semantically entailed (`validate_claim_citation_entailment`).
2. Japanese & English forbidden word / competitor check (`validate_words_and_competitors_jp_en`).
3. PII and secret scrubbing (`PIIRedactor` + `scan_for_secrets`).
Fails closed (`action='block'`) if Bedrock is unreachable.
"""

from __future__ import annotations

import asyncio
from typing import Any

from alba_one.guardrails.bedrock import (
    BedrockRuntimePort,
    FakeBedrockClient,
    run_parallel_bedrock_and_local,
)
from alba_one.guardrails.guardrails_ai import (
    validate_claim_citation_entailment,
    validate_words_and_competitors_jp_en,
)
from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.guardrails.types import (
    GuardrailContext,
    GuardrailResult,
    build_guardrail_result,
)
from alba_one.kb.pii import PIIRedactor


def run_local_output_validators(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    redactor: PIIRedactor | None = None,
) -> GuardrailResult:
    """Validate output citations, Japanese/English grounding entailment, words, secrets, and PII."""
    text = str(payload.get("text", ""))
    claims = payload.get("claims", [])
    sources: dict[str, str] = payload.get("available_sources_by_ref_id", {})

    if claims or payload.get("require_citations", True):
        ent_res = validate_claim_citation_entailment(
            claims=claims,
            available_sources_by_ref_id=sources,
            ctx=ctx,
        )
        if ent_res.details.get("detected_action") == "block":
            return ent_res

    word_res = validate_words_and_competitors_jp_en(text, ctx, layer="output")
    if word_res.details.get("detected_action") == "block":
        return word_res

    secrets = scan_for_secrets(text)
    if secrets:
        return build_guardrail_result(
            layer="output",
            raw_action="block",
            policy="output_secret_scrub",
            ctx=ctx,
            details={"leaked_secrets": secrets},
            refusal_key="blocked_output",
        )

    pii = (redactor or PIIRedactor()).redact(text)
    if pii.contains_pii:
        return build_guardrail_result(
            layer="output",
            raw_action="mask",
            policy="output_pii_scrub",
            ctx=ctx,
            details={"pii_counts": pii.counts},
            sanitized_payload=pii.redacted_text,
        )

    return build_guardrail_result(
        layer="output",
        raw_action="pass",
        policy="local_output_validators",
        ctx=ctx,
        sanitized_payload=text,
    )


async def check_async(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
) -> GuardrailResult:
    """Async Layer 3 check running Bedrock `OUTPUT` + grounding and local validators in parallel."""
    text = str(payload.get("text", ""))
    sources: dict[str, str] = payload.get("available_sources_by_ref_id", {})
    grounding_text = "\n".join(sources.values()) if sources else None
    client = bedrock_client or FakeBedrockClient()

    return await run_parallel_bedrock_and_local(
        bedrock_client=client,
        local_check_fn=lambda: run_local_output_validators(payload, ctx),
        text=text,
        source="OUTPUT",
        layer="output",
        ctx=ctx,
        grounding_source_text=grounding_text,
    )


def check(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
) -> GuardrailResult:
    """Synchronous entrypoint for `output_layer.check(payload, ctx) -> GuardrailResult`."""
    return asyncio.run(check_async(payload, ctx, bedrock_client=bedrock_client))
