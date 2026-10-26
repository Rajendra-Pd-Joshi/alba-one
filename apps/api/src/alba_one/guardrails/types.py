"""Shared types, event log, and `most_restrictive_wins` combiner for the 7 Guardrail layers (`guardrails/types.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

GuardrailActionType = Literal["pass", "escalate", "mask", "block"]
GuardrailModeType = Literal["enforce", "monitor"]

ACTION_PRIORITY: dict[str, int] = {
    "pass": 0,
    "escalate": 1,
    "mask": 2,
    "block": 3,
}

BILINGUAL_REFUSALS: dict[str, dict[str, str]] = {
    "blocked_input": {
        "ja": "恐れ入りますが、ご入力内容は安全または業務スコープのポリシーにより処理できません。業務上の意思決定に関する質問をご入力ください。",
        "en": "We cannot process this input due to safety or operational scope policies. Please submit an in-scope business decision query.",
    },
    "bedrock_unavailable": {
        "ja": "現在、安全検証サービス（ガードレール）が一時的に利用できないため、安全のため処理を停止しました。しばらくしてから再試行してください。",
        "en": "The safety verification service (guardrail) is temporarily unavailable. Failing closed for safety; please retry shortly.",
    },
    "blocked_output": {
        "ja": "生成された回答が根拠検証または安全ポリシーを満たさなかったため、出力を制限しました。",
        "en": "The generated output did not satisfy grounding or safety policies and was withheld.",
    },
}


@dataclass(frozen=True)
class GuardrailContext:
    """Per-request context passed to every guardrail layer `check(payload, ctx)`."""

    tenant_id: str
    user_id: str = "user_analyst_01"
    role: str = "analyst"
    lang: str = "ja"
    mode: GuardrailModeType = "enforce"
    decision_id: str | None = None


@dataclass(frozen=True)
class GuardrailEventRecord:
    """Immutable audit record matching the `guardrail_events` database table."""

    event_id: str
    tenant_id: str
    decision_id: str | None
    layer: str
    action: GuardrailActionType
    policy: str
    details: dict[str, Any]
    lang: str = "ja"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class GuardrailResult:
    """Unified return type for `check(payload, ctx) -> GuardrailResult(action, details)`."""

    layer: str
    action: GuardrailActionType
    policy: str
    details: dict[str, Any] = field(default_factory=dict)
    sanitized_payload: Any = None
    refusal_message: str | None = None
    event: GuardrailEventRecord | None = None


def build_guardrail_result(
    *,
    layer: str,
    raw_action: GuardrailActionType,
    policy: str,
    ctx: GuardrailContext,
    details: dict[str, Any] | None = None,
    sanitized_payload: Any = None,
    refusal_key: str | None = None,
) -> GuardrailResult:
    """Construct a `GuardrailResult` and `GuardrailEventRecord`, applying `monitor` (Detect) vs `enforce` mode."""
    info = dict(details or {})
    info["configured_mode"] = ctx.mode
    info["detected_action"] = raw_action

    # In monitor mode (mapped to Bedrock Detect mode), log the detected action in details,
    # but downgrade blocking/masking to "pass" so traffic is only observed.
    effective_action: GuardrailActionType = (
        "pass" if (ctx.mode == "monitor" and raw_action != "pass") else raw_action
    )

    refusal_msg: str | None = None
    if refusal_key and refusal_key in BILINGUAL_REFUSALS:
        lang_key = "ja" if ctx.lang == "ja" else "en"
        refusal_msg = BILINGUAL_REFUSALS[refusal_key][lang_key]

    event = GuardrailEventRecord(
        event_id=f"grev_{uuid.uuid4().hex[:12]}",
        tenant_id=ctx.tenant_id,
        decision_id=ctx.decision_id,
        layer=layer,
        action=raw_action,
        policy=policy,
        details=info,
        lang=ctx.lang,
    )
    return GuardrailResult(
        layer=layer,
        action=effective_action,
        policy=policy,
        details=info,
        sanitized_payload=sanitized_payload,
        refusal_message=refusal_msg,
        event=event,
    )


def most_restrictive_wins(
    results: Sequence[GuardrailResult],
    *,
    ctx: GuardrailContext,
    layer: str,
) -> GuardrailResult:
    """Combine parallel guardrail results using `block > mask > escalate > pass`."""
    if not results:
        return build_guardrail_result(layer=layer, raw_action="pass", policy="none", ctx=ctx)

    chosen = max(
        results,
        key=lambda r: ACTION_PRIORITY.get(r.details.get("detected_action", r.action), 0),
    )
    combined_details: dict[str, Any] = {
        "engines_evaluated": [
            {
                "policy": r.policy,
                "detected_action": r.details.get("detected_action", r.action),
                "details": r.details,
            }
            for r in results
        ]
    }
    sanitized = chosen.sanitized_payload
    if sanitized is None:
        for r in results:
            if r.sanitized_payload is not None:
                sanitized = r.sanitized_payload
                break

    raw_winner: GuardrailActionType = chosen.details.get("detected_action", chosen.action)
    refusal_key = None
    if raw_winner == "block":
        if chosen.policy == "bedrock_unavailable_fail_closed":
            refusal_key = "bedrock_unavailable"
        elif layer == "output":
            refusal_key = "blocked_output"
        else:
            refusal_key = "blocked_input"

    return build_guardrail_result(
        layer=layer,
        raw_action=raw_winner,
        policy=chosen.policy,
        ctx=ctx,
        details=combined_details,
        sanitized_payload=sanitized,
        refusal_key=refusal_key,
    )
