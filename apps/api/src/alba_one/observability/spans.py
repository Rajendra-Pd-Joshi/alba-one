"""Unified Span Schema & Privacy-by-Default Sanitizer (`observability/spans.py`).

Per Phase 9 User Answer 1:
- Exact 16 `PhaseStepType` values and 6 `SpanKindType` values.
- Privacy by default: spans store SHA-256 hashes (`prompt_hash`, `output_hash`) and byte sizes
  (`prompt_bytes`, `output_bytes`), NOT raw text, unless `TRACE_CAPTURE_CONTENT=true`.
- Even when `TRACE_CAPTURE_CONTENT=true`, all text passes through `PIIRedactor` and secret-canary
  scrubbing first so secrets and PII never enter span attributes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import os
import re
from typing import Any, Literal

from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.kb.pii import PIIRedactor

PhaseStepType = Literal[
    "clarify",
    "rewrite",
    "retrieve",
    "rerank",
    "embed",
    "input_guardrail",
    "retriever_guardrail",
    "plan",
    "tool_call",
    "hypothesis",
    "confidence",
    "judge",
    "output_guardrail",
    "memory",
    "approval_resume",
    "writeback",
]

ALL_PHASE_STEPS: tuple[PhaseStepType, ...] = (
    "clarify",
    "rewrite",
    "retrieve",
    "rerank",
    "embed",
    "input_guardrail",
    "retriever_guardrail",
    "plan",
    "tool_call",
    "hypothesis",
    "confidence",
    "judge",
    "output_guardrail",
    "memory",
    "approval_resume",
    "writeback",
)

SpanKindType = Literal["llm", "embedding", "rerank", "guardrail", "mcp_tool", "calc"]
SpanStatusType = Literal["ok", "error", "timeout", "blocked", "cache_hit"]

_CANARY_SECRET_RE = re.compile(r"CANARY-[0-9A-Fa-f]{6,32}|sk-[A-Za-z0-9]{12,}|AKIA[0-9A-Z]{16}")


def scrub_span_text(text: str | None, *, capture_content: bool = False) -> tuple[str, int, str | None]:
    """Return `(sha256_hash, byte_size, optional_redacted_text)` with zero secret/canary leakage."""
    raw = text or ""
    raw_bytes = raw.encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if not capture_content:
        return digest, len(raw_bytes), None

    # Scrub synthetic secret canaries, API keys, and JP/EN PII before storing
    no_secrets = _CANARY_SECRET_RE.sub("[REDACTED_SECRET]", raw)
    if scan_for_secrets(no_secrets):
        no_secrets = "[REDACTED_SECRET_PAYLOAD]"
    pii_clean = PIIRedactor().redact(no_secrets).redacted_text
    return digest, len(raw_bytes), pii_clean


@dataclass
class SpanRecord:
    """One span row per LLM, embedding, rerank, guardrail, MCP tool, or calculator call."""

    span_id: str
    parent_span_id: str | None
    trace_id: str
    tenant_id: str
    decision_id: str | None
    run_id: str
    attempt: int
    phase_step: PhaseStepType
    kind: SpanKindType
    model_or_tool: str
    provider: str
    prompt_version: str | None
    guardrail_version: str | None
    model_config_version: str | None
    tool_def_hash: str | None
    app_version: str
    lang: str
    tokens_in: int
    tokens_out: int
    tokens_estimated: bool
    latency_ms: float
    ttfb_ms: float | None
    status: SpanStatusType
    error_type: str | None
    retry_count: int
    cache_hit: bool
    cost_amount: float | None
    cost_currency: str
    price_table_version: str
    cost_estimated: bool
    prompt_hash: str = ""
    prompt_bytes: int = 0
    output_hash: str = ""
    output_bytes: int = 0
    captured_prompt_redacted: str | None = None
    captured_output_redacted: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_trace_capture_enabled(env_override: bool | None = None) -> bool:
    """Return whether raw (PII-redacted) prompt/response capture is enabled (`TRACE_CAPTURE_CONTENT`)."""
    if env_override is not None:
        return env_override
    return os.getenv("TRACE_CAPTURE_CONTENT", "false").lower() in ("1", "true", "yes")
