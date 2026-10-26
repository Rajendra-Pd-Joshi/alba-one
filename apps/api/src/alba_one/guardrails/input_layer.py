"""Layer 2: Input Guardrail (`guardrails/input_layer.py`).

Runs AWS Bedrock `ApplyGuardrail(source='INPUT')` in parallel (`asyncio.gather`)
with local deterministic validators:
1. Prompt injection & jailbreak scan (JP + EN).
2. Denied topic / out-of-scope check (medical/legal/unrelated).
3. Japanese & English forbidden word / competitor check (`guardrails_ai.py`).
4. Japanese & English PII masking (`PIIRedactor`) and secret leak scan.
Combines results via `most_restrictive_wins` (`block > mask > escalate > pass`).
If Bedrock is unreachable, fails closed (`action='block'`).
"""

from __future__ import annotations

import asyncio
from typing import Any

from alba_one.guardrails.bedrock import (
    BedrockRuntimePort,
    FakeBedrockClient,
    run_parallel_bedrock_and_local,
)
from alba_one.guardrails.guardrails_ai import validate_words_and_competitors_jp_en
from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.guardrails.types import (
    GuardrailContext,
    GuardrailResult,
    build_guardrail_result,
    most_restrictive_wins,
)
from alba_one.kb.pii import PIIRedactor
from alba_one.retrieval.guardrail_stub import has_prompt_injection

_OUT_OF_SCOPE_PATTERNS: tuple[str, ...] = (
    "処方薬と診断名",
    "脱税スキーム",
    "diagnose my medical symptoms",
    "tax evasion scheme",
)


def run_local_input_validators(
    text: str,
    ctx: GuardrailContext,
    *,
    redactor: PIIRedactor | None = None,
) -> GuardrailResult:
    """Cheap deterministic local validators executed in parallel with Bedrock `ApplyGuardrail`."""
    inj = has_prompt_injection(text)
    if inj:
        return build_guardrail_result(
            layer="input",
            raw_action="block",
            policy="local_prompt_injection_check",
            ctx=ctx,
            details={"matched_pattern": inj},
            refusal_key="blocked_input",
        )

    lowered = text.lower()
    for pat in _OUT_OF_SCOPE_PATTERNS:
        if pat in lowered:
            return build_guardrail_result(
                layer="input",
                raw_action="block",
                policy="local_denied_topic_scope",
                ctx=ctx,
                details={"matched_topic": pat},
                refusal_key="blocked_input",
            )

    word_res = validate_words_and_competitors_jp_en(text, ctx, layer="input")
    if word_res.details.get("detected_action") == "block":
        return word_res

    secrets = scan_for_secrets(text)
    if secrets:
        return build_guardrail_result(
            layer="input",
            raw_action="block",
            policy="local_secret_leak_check",
            ctx=ctx,
            details={"leaked_secrets": secrets},
            refusal_key="blocked_input",
        )

    pii = (redactor or PIIRedactor()).redact(text)
    if pii.contains_pii:
        return build_guardrail_result(
            layer="input",
            raw_action="mask",
            policy="local_jp_en_pii_redactor",
            ctx=ctx,
            details={"pii_counts": pii.counts},
            sanitized_payload=pii.redacted_text,
        )

    return build_guardrail_result(
        layer="input",
        raw_action="pass",
        policy="local_input_validators",
        ctx=ctx,
        sanitized_payload=text,
    )


async def check_async(
    payload: str | dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
) -> GuardrailResult:
    """Async Layer 2 check running Bedrock `INPUT` and local validators concurrently via `asyncio.gather`."""
    text = payload if isinstance(payload, str) else str(payload.get("text", ""))
    client = bedrock_client or FakeBedrockClient()
    return await run_parallel_bedrock_and_local(
        bedrock_client=client,
        local_check_fn=lambda: run_local_input_validators(text, ctx),
        text=text,
        source="INPUT",
        layer="input",
        ctx=ctx,
    )


def check(
    payload: str | dict[str, Any],
    ctx: GuardrailContext,
    *,
    bedrock_client: BedrockRuntimePort | None = None,
) -> GuardrailResult:
    """Synchronous entrypoint for `input_layer.check(payload, ctx) -> GuardrailResult`."""
    return asyncio.run(check_async(payload, ctx, bedrock_client=bedrock_client))
