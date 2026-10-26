"""Layer 6: Human-in-the-Loop (HITL) Guardrail (`guardrails/hitl_layer.py`).

Enforces Principle 4 ("Humans decide"):
- Policy table defining which actions, risk levels, and confidence thresholds force
  human approval (`escalate`), which RBAC roles may approve (`approver`, `admin`),
  approval SLA timeout (`approval_timeout_seconds`), and escalation target role.
- Blocks any attempt by a non-approver (`viewer`, `analyst`) to record an approval,
  or any approval/rejection missing a mandatory human reason.
"""

from __future__ import annotations

from typing import Any

from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result

HITL_POLICY_TABLE: dict[str, Any] = {
    "allowed_approver_roles": frozenset({"approver", "admin"}),
    "min_auto_pass_confidence": 0.80,
    "force_approval_on_write_tools": True,
    "force_approval_on_final_recommendation": True,
    "approval_timeout_seconds": 14400,  # 4 hours before escalating to executive_ops / admin
    "escalation_target_role": "admin",
}


def check(payload: dict[str, Any], ctx: GuardrailContext) -> GuardrailResult:
    """Layer 6 `check(payload, ctx) -> GuardrailResult` for HITL gating and approval verification."""
    event_kind = str(payload.get("kind", "recommendation_gate"))
    confidence = float(payload.get("confidence", 0.0))
    risk_level = str(payload.get("risk_level", "medium")).lower()
    is_write_action = bool(payload.get("is_write_action", False))
    approval_record: dict[str, Any] | None = payload.get("approval_record")
    elapsed_wait_seconds = int(payload.get("elapsed_wait_seconds", 0))

    # Case 1: Validating a submitted human approval/rejection action
    if event_kind == "submit_approval" or approval_record is not None:
        rec = approval_record or payload
        approver_role = str(rec.get("approver_role") or ctx.role).lower()
        reason = str(rec.get("reason", "")).strip()
        if approver_role not in HITL_POLICY_TABLE["allowed_approver_roles"]:
            return build_guardrail_result(
                layer="hitl",
                raw_action="block",
                policy="hitl_approver_role_required",
                ctx=ctx,
                details={
                    "caller_role": approver_role,
                    "allowed_roles": sorted(HITL_POLICY_TABLE["allowed_approver_roles"]),
                },
            )
        if not reason:
            return build_guardrail_result(
                layer="hitl",
                raw_action="block",
                policy="hitl_approval_reason_required",
                ctx=ctx,
                details={"error": "Approval or rejection requires a non-empty reason."},
            )
        return build_guardrail_result(
            layer="hitl",
            raw_action="pass",
            policy="hitl_approval_verified",
            ctx=ctx,
            details={
                "approver_role": approver_role,
                "action": rec.get("action", "approve"),
                "reason": reason,
            },
            sanitized_payload=rec,
        )

    # Case 2: Evaluating whether an action/recommendation must pause for human approval
    timeout_sec = int(HITL_POLICY_TABLE["approval_timeout_seconds"])
    if elapsed_wait_seconds > timeout_sec:
        return build_guardrail_result(
            layer="hitl",
            raw_action="escalate",
            policy="hitl_approval_timeout_escalation",
            ctx=ctx,
            details={
                "elapsed_wait_seconds": elapsed_wait_seconds,
                "timeout_seconds": timeout_sec,
                "escalate_to_role": HITL_POLICY_TABLE["escalation_target_role"],
            },
        )

    needs_approval = (
        is_write_action
        or risk_level in ("high", "critical")
        or confidence < float(HITL_POLICY_TABLE["min_auto_pass_confidence"])
        or bool(payload.get("is_final_recommendation", False))
    )
    if needs_approval:
        return build_guardrail_result(
            layer="hitl",
            raw_action="escalate",
            policy="hitl_human_approval_gate",
            ctx=ctx,
            details={
                "requires_human_approval": True,
                "confidence": confidence,
                "risk_level": risk_level,
                "is_write_action": is_write_action,
                "allowed_approver_roles": sorted(HITL_POLICY_TABLE["allowed_approver_roles"]),
                "timeout_seconds": timeout_sec,
            },
        )

    return build_guardrail_result(
        layer="hitl",
        raw_action="pass",
        policy="hitl_readonly_low_risk",
        ctx=ctx,
        details={"confidence": confidence, "risk_level": risk_level},
    )
