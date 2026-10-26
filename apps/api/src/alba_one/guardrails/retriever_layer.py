"""Layer 4: Retriever Guardrail (`guardrails/retriever_layer.py`).

Enforces on every retrieved KB chunk or external search result:
1. Tenant isolation (`chunk.tenant_id == ctx.tenant_id`) and ACL tag check (`role:{ctx.role}`).
2. AWS Bedrock `ApplyGuardrail(source='INPUT')` + local prompt-injection heuristics in parallel.
3. PII masking (`PIIRedactor`) before chunk text reaches any LLM.
Poisoned or unauthorized chunks are dropped and logged as `GuardrailEventRecord`s.
"""

from __future__ import annotations

import asyncio
from typing import Any

from alba_one.guardrails.bedrock import (
    BedrockRuntimePort,
    FakeBedrockClient,
    run_parallel_bedrock_and_local,
)
from alba_one.guardrails.types import (
    GuardrailContext,
    GuardrailResult,
    build_guardrail_result,
)
from alba_one.kb.pii import PIIRedactor
from alba_one.retrieval.guardrail_stub import has_prompt_injection


def _local_chunk_check(chunk: dict[str, Any], ctx: GuardrailContext, redactor: PIIRedactor) -> GuardrailResult:
    cid = str(chunk.get("chunk_id", "unknown"))
    if not chunk.get("external") and chunk.get("tenant_id") != ctx.tenant_id:
        return build_guardrail_result(
            layer="retriever",
            raw_action="block",
            policy="retriever_tenant_isolation",
            ctx=ctx,
            details={"chunk_id": cid},
        )

    acls = set(chunk.get("acl_tags", []))
    allowed_acl = {f"role:{ctx.role.strip().lower()}"}
    if acls and not (acls & allowed_acl):
        return build_guardrail_result(
            layer="retriever",
            raw_action="block",
            policy="retriever_acl_enforcement",
            ctx=ctx,
            details={"chunk_id": cid, "required_acl": sorted(acls), "caller_role": ctx.role},
        )

    raw_text = str(chunk.get("text", ""))
    inj = has_prompt_injection(raw_text)
    if inj:
        return build_guardrail_result(
            layer="retriever",
            raw_action="block",
            policy="retriever_prompt_injection_scan",
            ctx=ctx,
            details={"chunk_id": cid, "matched": inj},
        )

    pii = redactor.redact(raw_text)
    sanitized = dict(chunk)
    sanitized["text"] = pii.redacted_text
    if pii.contains_pii:
        return build_guardrail_result(
            layer="retriever",
            raw_action="mask",
            policy="retriever_pii_redaction",
            ctx=ctx,
            details={"chunk_id": cid, "pii_counts": pii.counts},
            sanitized_payload=sanitized,
        )

    return build_guardrail_result(
        layer="retriever",
        raw_action="pass",
        policy="retriever_chunk_clean",
        ctx=ctx,
        details={"chunk_id": cid},
        sanitized_payload=sanitized,
    )


async def check_chunk_async(
    chunk: dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
    redactor: PIIRedactor | None = None,
) -> GuardrailResult:
    """Evaluate a single retrieved chunk with Bedrock `INPUT` and local ACL/PII/injection checks in parallel."""
    red = redactor or PIIRedactor()
    local_res = _local_chunk_check(chunk, ctx, red)
    if local_res.details.get("detected_action") == "block":
        return local_res

    client = bedrock_client or FakeBedrockClient()
    return await run_parallel_bedrock_and_local(
        bedrock_client=client,
        local_check_fn=lambda: local_res,
        text=str(chunk.get("text", "")),
        source="INPUT",
        layer="retriever",
        ctx=ctx,
    )


def check(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
) -> GuardrailResult:
    """Synchronous Layer 4 entrypoint: `check(chunk_dict, ctx) -> GuardrailResult`."""
    return asyncio.run(check_chunk_async(payload, ctx, bedrock_client=bedrock_client))
