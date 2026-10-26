"""Incident Sanitisation, Containment Recommendations & Scoped Degraded Mode (`redteam/incidents.py` — Phase 11).

Enforces:
- Untrusted output handling: attack prompts and model outputs are NEVER pasted raw into issue bodies,
  chat notifications, or alerts that an LLM assistant or browser might render. They are truncated,
  HTML/Markdown-escaped, stripped of backticks/directive tags, and wrapped in a code block with an
  explicit `[WARNING: UNTRUSTED ADVERSARIAL ARTIFACT]` banner.
- Containment response:
  - NEVER auto-triggers `OPS_KILL_SWITCH=true`.
  - Default mode `recommend`: ranks containment options by blast radius (1. Roll back release,
    2. Flip scoped feature flag e.g. `ALLOW_EXTERNAL_FALLBACK=false` or `READ_ONLY_TOOLS_ONLY=true`,
    3. Full `OPS_KILL_SWITCH=true` by human choice).
  - Optional `degraded_mode`: only if `degraded_mode_approved_by` is signed off (not `TODO(owner)`),
    flips ONLY pre-approved scoped flags (`ALLOW_EXTERNAL_FALLBACK=false`, `READ_ONLY_TOOLS_ONLY=true`)
    for deterministic categories (`cross_tenant_isolation`, `hitl_and_write_tool_bypass`,
    `pii_and_canary_exfiltration`), logs the triggering `run_id`, and includes a one-command undo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import logging
import re
from typing import Any, Literal

from redteam.compare import ComparisonReport

logger = logging.getLogger(__name__)

DETERMINISTIC_DEGRADED_CATEGORIES: frozenset[str] = frozenset(
    {
        "cross_tenant_isolation",
        "hitl_and_write_tool_bypass",
        "pii_and_canary_exfiltration",
        "outbound_query_codename_leak",
    }
)

SCOPED_ALLOWED_FLAGS: tuple[str, ...] = (
    "ALLOW_EXTERNAL_FALLBACK=false",
    "READ_ONLY_TOOLS_ONLY=true",
)


def sanitize_untrusted_for_incident(raw_text: str, *, max_chars: int = 240) -> str:
    """Truncate, escape HTML/Markdown/backticks, and wrap untrusted text in a warning code block."""
    cleaned = str(raw_text or "")
    # Neutralize fenced code blocks, HTML tags, and markdown image/link injections
    cleaned = cleaned.replace("```", "'''").replace("`", "'")
    cleaned = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r"[escaped-image:\1]", cleaned)
    cleaned = html.escape(cleaned, quote=True)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "... [TRUNCATED]"
    return (
        "```text\n"
        "[WARNING: UNTRUSTED ADVERSARIAL ARTIFACT — DO NOT FEED TO LLM AGENTS WITHOUT GUARDRAIL SCAN]\n"
        f"{cleaned}\n"
        "```"
    )


@dataclass(frozen=True)
class ContainmentDecision:
    """Structured containment decision for a critical red-team regression."""

    mode: Literal["off", "recommend", "degraded_mode"]
    kill_switch_triggered: bool  # Invariant: ALWAYS False in automated code
    applied_scoped_flags: list[str]
    recommended_options_ranked: list[str]
    one_command_undo: str
    runbook_url: str
    triggering_run_id: str


def evaluate_containment(
    *,
    run_id: str,
    critical_bypass_count: int,
    failing_categories: list[str],
    containment_mode: Literal["off", "recommend", "degraded_mode"] = "recommend",
    degraded_mode_approved_by: str = "TODO(owner)",
) -> ContainmentDecision:
    """Compute containment actions. Invariant: NEVER auto-triggers `OPS_KILL_SWITCH`."""
    runbook = "https://github.com/albaconnect/alba-one/blob/main/docs/RUNBOOK.md"
    ranked_recommendations = [
        "1. [Smallest Blast Radius] Roll back canary / latest release via Argo Rollouts (`kubectl argo rollouts undo alba-one-api -n alba-one-prod`).",
        "2. [Scoped Feature Flag] Disable external search and write-class MCP tools (`ALLOW_EXTERNAL_FALLBACK=false`, `READ_ONLY_TOOLS_ONLY=true`).",
        "3. [Full Emergency Halt — Human Decision Only] Set `OPS_KILL_SWITCH=true` if active cross-tenant exfiltration is confirmed.",
    ]
    undo_cmd = (
        "kubectl set env deployment/alba-one-api -n alba-one-prod "
        "ALLOW_EXTERNAL_FALLBACK=true READ_ONLY_TOOLS_ONLY=false"
    )

    applied_flags: list[str] = []
    if (
        critical_bypass_count > 0
        and containment_mode == "degraded_mode"
        and degraded_mode_approved_by.strip()
        and not degraded_mode_approved_by.strip().startswith("TODO(")
    ):
        if any(cat in DETERMINISTIC_DEGRADED_CATEGORIES for cat in failing_categories):
            applied_flags = list(SCOPED_ALLOWED_FLAGS)
            logger.warning(
                "redteam_auto_degraded_mode_activated",
                extra={
                    "triggering_run_id": run_id,
                    "applied_scoped_flags": applied_flags,
                    "undo_command": undo_cmd,
                },
            )

    return ContainmentDecision(
        mode=containment_mode,
        kill_switch_triggered=False,
        applied_scoped_flags=applied_flags,
        recommended_options_ranked=ranked_recommendations,
        one_command_undo=undo_cmd,
        runbook_url=runbook,
        triggering_run_id=run_id,
    )


@dataclass(frozen=True)
class IncidentArtifact:
    """Sanitized issue/alert payload for critical bypasses or over-refusal spikes."""

    severity: Literal["critical", "warning"]
    title: str
    body_markdown: str
    page_human: bool
    requires_regression_corpus_before_close: bool
    attached_trace_ids: list[str] = field(default_factory=list)


def build_incident_artifact(
    *,
    run_id: str,
    app_version: str,
    diff: ComparisonReport,
    containment: ContainmentDecision,
    trace_ids: list[str],
    untrusted_sample_excerpt: str = "",
) -> IncidentArtifact:
    """Build a sanitized Markdown incident issue without raw prompt/output injection."""
    safe_excerpt = sanitize_untrusted_for_incident(untrusted_sample_excerpt)
    if diff.critical_bypass_count > 0:
        title = f"[SECURITY CRITICAL] Red-Team Bypass Detected on {app_version} (run={run_id})"
        lines = [
            f"## Critical Red-Team Regression (`run_id={run_id}`, `version={app_version}`)",
            f"- **Critical Bypasses**: `{diff.critical_bypass_count}`",
            f"- **New Failing Scenario IDs**: `{', '.join(diff.new_critical_bypasses) or 'see attached JSON'}`",
            f"- **Trace IDs**: `{', '.join(trace_ids[:10])}`",
            f"- **Runbook**: {containment.runbook_url}",
            "- **Closure Policy**: Must add regression fixture under `redteam/corpus/` and pass retest before human closure.",
            "### Recommended Containment Options (Ranked by Blast Radius)",
            *[f"- {opt}" for opt in containment.recommended_options_ranked],
            f"- **One-Command Undo for Scoped Flags**: `{containment.one_command_undo}`",
            "### Sanitized Excerpt (Full Payload in Attached Artifact Only)",
            safe_excerpt,
        ]
        return IncidentArtifact(
            severity="critical",
            title=title,
            body_markdown="\n".join(lines),
            page_human=True,
            requires_regression_corpus_before_close=True,
            attached_trace_ids=list(trace_ids),
        )

    title = f"[QUALITY WARNING] Guardrail Over-Refusal Spike on {app_version} (run={run_id})"
    lines = [
        f"## Benign Over-Refusal Regression (`run_id={run_id}`, `version={app_version}`)",
        f"- **Comparability**: `{diff.comparability_note}`",
        f"- **Attributed Version Changes**: `{diff.attributed_version_changes}`",
        f"- **Newly Blocked Benign Scenarios**: `{diff.newly_blocked_benign}`",
        "### Sanitized Excerpt",
        safe_excerpt,
    ]
    return IncidentArtifact(
        severity="warning",
        title=title,
        body_markdown="\n".join(lines),
        page_human=False,
        requires_regression_corpus_before_close=False,
        attached_trace_ids=list(trace_ids),
    )
