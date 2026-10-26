"""AWS Bedrock Guardrails runtime client, `FakeBedrockClient`, and parallel `asyncio.gather` executor (`guardrails/bedrock.py`).

Implements User Answer 1:
- Calls `bedrock-runtime.apply_guardrail` in parallel (`asyncio.gather`) with cheap
  deterministic local validators, combining results via `most_restrictive_wins`
  (`block > mask > escalate > pass`).
- Maps `monitor` mode to non-blocking detection logging and `enforce` to blocking/masking.
- Fail-closed policy: if Bedrock is unreachable on `INPUT` or `OUTPUT`, returns `action="block"`
  with `policy="bedrock_unavailable_fail_closed"` and a polite bilingual refusal while still
  running and recording the local deterministic validators.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal, Protocol

from alba_one.guardrails.types import (
    GuardrailActionType,
    GuardrailContext,
    GuardrailResult,
    build_guardrail_result,
    most_restrictive_wins,
)
from alba_one.kb.pii import PIIRedactor
from alba_one.retrieval.guardrail_stub import has_prompt_injection


class BedrockRuntimePort(Protocol):
    """Minimal interface matching `boto3.client('bedrock-runtime').apply_guardrail`."""

    def apply_guardrail(
        self,
        *,
        guardrailIdentifier: str,
        guardrailVersion: str,
        source: Literal["INPUT", "OUTPUT"],
        content: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class Boto3BedrockRuntimeClient:
    """Production wrapper around `boto3.client('bedrock-runtime')`."""

    def __init__(self, region_name: str = "ap-northeast-1") -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def apply_guardrail(
        self,
        *,
        guardrailIdentifier: str,
        guardrailVersion: str,
        source: Literal["INPUT", "OUTPUT"],
        content: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._client.apply_guardrail(
            guardrailIdentifier=guardrailIdentifier,
            guardrailVersion=guardrailVersion,
            source=source,
            content=content,
        )


_DENIED_TOPIC_PATTERNS: tuple[str, ...] = (
    "処方薬と診断名",
    "脱税スキーム",
    "diagnose my medical symptoms",
    "tax evasion scheme",
    "爆弾の製造",
    "build a bomb",
)


class FakeBedrockClient:
    """Deterministic `BedrockRuntimePort` test double for unit tests (never calls AWS)."""

    def __init__(self, *, raise_unreachable: bool = False) -> None:
        self.raise_unreachable = raise_unreachable
        self.calls: list[dict[str, Any]] = []
        self._redactor = PIIRedactor()

    def apply_guardrail(
        self,
        *,
        guardrailIdentifier: str,
        guardrailVersion: str,
        source: Literal["INPUT", "OUTPUT"],
        content: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "guardrailIdentifier": guardrailIdentifier,
                "guardrailVersion": guardrailVersion,
                "source": source,
                "content": content,
            }
        )
        if self.raise_unreachable:
            raise ConnectionError("Simulated AWS Bedrock endpoint unreachable (timeout/503)")

        text_parts = [
            str(block.get("text", {}).get("text", ""))
            for block in content
            if isinstance(block, dict) and "text" in block
        ]
        joined = "\n".join(text_parts)
        lowered = joined.lower()

        if has_prompt_injection(joined):
            return {
                "action": "GUARDRAIL_INTERVENED",
                "outputs": [{"text": "Blocked by Bedrock PROMPT_ATTACK filter."}],
                "assessments": [{"contentPolicy": {"filters": [{"type": "PROMPT_ATTACK", "action": "BLOCKED"}]}}],
            }

        for topic_kw in _DENIED_TOPIC_PATTERNS:
            if topic_kw in lowered:
                return {
                    "action": "GUARDRAIL_INTERVENED",
                    "outputs": [{"text": "Blocked by Bedrock Denied Topic filter."}],
                    "assessments": [{"topicPolicy": {"topics": [{"name": "denied_topic", "action": "BLOCKED"}]}}],
                }

        pii_res = self._redactor.redact(joined)
        if pii_res.contains_pii:
            return {
                "action": "GUARDRAIL_INTERVENED",
                "outputs": [{"text": pii_res.redacted_text}],
                "assessments": [
                    {
                        "sensitiveInformationPolicy": {
                            "regexes": [{"name": k, "action": "ANONYMIZED"} for k in pii_res.counts]
                        }
                    }
                ],
            }

        return {"action": "NONE", "outputs": [{"text": joined}], "assessments": []}


async def invoke_bedrock_guardrail_async(
    client: BedrockRuntimePort,
    *,
    text: str,
    source: Literal["INPUT", "OUTPUT"],
    layer: str,
    ctx: GuardrailContext,
    guardrail_id: str = "gr-alba-standard",
    guardrail_version: str = "1",
    grounding_source_text: str | None = None,
) -> GuardrailResult:
    """Call `apply_guardrail` in a worker thread and enforce fail-closed on connection errors."""
    content_blocks: list[dict[str, Any]] = []
    if grounding_source_text and source == "OUTPUT":
        content_blocks.append({"text": {"text": grounding_source_text, "qualifiers": ["grounding_source"]}})
        content_blocks.append({"text": {"text": text, "qualifiers": ["guard_content"]}})
    else:
        content_blocks.append({"text": {"text": text}})

    try:
        resp = await asyncio.to_thread(
            client.apply_guardrail,
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,
            source=source,
            content=content_blocks,
        )
    except Exception as exc:
        # Fail-closed per docs/FAILURE_POLICY.md when Bedrock is unreachable
        return build_guardrail_result(
            layer=layer,
            raw_action="block",
            policy="bedrock_unavailable_fail_closed",
            ctx=ctx,
            details={"error": str(exc), "fail_closed": True, "source": source},
            refusal_key="bedrock_unavailable",
        )

    action_str = str(resp.get("action", "NONE"))
    assessments = resp.get("assessments", [])
    outputs = resp.get("outputs", [])
    out_text = str(outputs[0].get("text", text)) if outputs else text

    if action_str == "GUARDRAIL_INTERVENED":
        # Distinguish ANONYMIZED (mask) from BLOCKED (block)
        serialized = str(assessments)
        if "ANONYMIZED" in serialized and "BLOCKED" not in serialized:
            raw_act: GuardrailActionType = "mask"
            policy_name = "bedrock_pii_anonymize"
        else:
            raw_act = "block"
            policy_name = "bedrock_policy_intervened"
        return build_guardrail_result(
            layer=layer,
            raw_action=raw_act,
            policy=policy_name,
            ctx=ctx,
            details={"bedrock_action": action_str, "assessments": assessments},
            sanitized_payload=out_text if raw_act == "mask" else None,
            refusal_key="blocked_output" if source == "OUTPUT" else "blocked_input",
        )

    return build_guardrail_result(
        layer=layer,
        raw_action="pass",
        policy="bedrock_apply_guardrail",
        ctx=ctx,
        details={"bedrock_action": "NONE"},
        sanitized_payload=text,
    )


async def run_parallel_bedrock_and_local(
    *,
    bedrock_client: BedrockRuntimePort,
    local_check_fn: Callable[[], GuardrailResult],
    text: str,
    source: Literal["INPUT", "OUTPUT"],
    layer: str,
    ctx: GuardrailContext,
    guardrail_id: str = "gr-alba-standard",
    guardrail_version: str = "1",
    grounding_source_text: str | None = None,
) -> GuardrailResult:
    """Run Bedrock `apply_guardrail` and `local_check_fn` concurrently via `asyncio.gather`."""
    bedrock_coro = invoke_bedrock_guardrail_async(
        bedrock_client,
        text=text,
        source=source,
        layer=layer,
        ctx=ctx,
        guardrail_id=guardrail_id,
        guardrail_version=guardrail_version,
        grounding_source_text=grounding_source_text,
    )
    local_coro = asyncio.to_thread(local_check_fn)
    bedrock_res, local_res = await asyncio.gather(bedrock_coro, local_coro)
    return most_restrictive_wins([bedrock_res, local_res], ctx=ctx, layer=layer)
