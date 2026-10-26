"""# STUB: Retriever guardrail interface for Phase 3 (`retrieval/guardrail_stub.py`).

Wired to full AWS Bedrock `ApplyGuardrail` + Guardrails AI in Phase 4.
In Phase 3, every retrieved KB chunk and every `ExternalResult` passes through:
1. ACL check (`caller_acl_tags` intersection for KB chunks).
2. PII redaction (`PIIRedactor` from `kb/pii.py`).
3. Prompt-injection heuristic scan (drops poisoned chunks/results attempting instruction override).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from alba_one.kb.pii import PIIRedactor
from alba_one.retrieval.ports import ExternalResult

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*[:=]", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"これまでの指示を(?:すべて|全て)?無視", re.IGNORECASE),
    re.compile(r"システムプロンプトを(?:開示|出力)", re.IGNORECASE),
    re.compile(r"管理者権限で強制承認", re.IGNORECASE),
)


@dataclass(frozen=True)
class GuardrailScanStats:
    """Summary of chunks/external results scanned, masked, or blocked by the retriever guardrail."""

    scanned_count: int = 0
    passed_count: int = 0
    masked_pii_count: int = 0
    dropped_acl_count: int = 0
    dropped_injection_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


def has_prompt_injection(text: str) -> str | None:
    """Return the matched injection pattern string if `text` contains a prompt-injection payload."""
    for pat in _INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


class RetrieverGuardrailStub:
    """# STUB: Phase 3 retriever guardrail enforcing ACLs, PII scrubbing, and injection filtering."""

    def __init__(self, redactor: PIIRedactor | None = None) -> None:
        self._redactor = redactor or PIIRedactor()

    def filter_kb_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        tenant_id: str,
        caller_role: str,
    ) -> tuple[list[dict[str, Any]], GuardrailScanStats]:
        """Filter and scrub KB chunks before they reach any LLM prompt."""
        allowed_acl = {f"role:{caller_role.strip().lower()}"}
        cleaned: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        masked_pii = dropped_acl = dropped_inj = 0

        for chk in chunks:
            cid = str(chk.get("chunk_id", ""))
            if chk.get("tenant_id") != tenant_id:
                dropped_acl += 1
                events.append({"layer": "retriever", "action": "block", "policy": "tenant_isolation", "ref_id": cid})
                continue

            acls = set(chk.get("acl_tags", []))
            if acls and not (acls & allowed_acl):
                dropped_acl += 1
                events.append({"layer": "retriever", "action": "block", "policy": "acl_tag_check", "ref_id": cid})
                continue

            raw_text = str(chk.get("text", ""))
            inj_match = has_prompt_injection(raw_text)
            if inj_match:
                dropped_inj += 1
                events.append(
                    {
                        "layer": "retriever",
                        "action": "block",
                        "policy": "prompt_injection_scan",
                        "ref_id": cid,
                        "matched": inj_match,
                    }
                )
                continue

            pii_res = self._redactor.redact(raw_text)
            item = dict(chk)
            item["text"] = pii_res.redacted_text
            if "parent_text" in item and item["parent_text"]:
                item["parent_text"] = self._redactor.redact(str(item["parent_text"])).redacted_text
            if pii_res.contains_pii:
                masked_pii += 1
                events.append(
                    {
                        "layer": "retriever",
                        "action": "mask",
                        "policy": "pii_redaction",
                        "ref_id": cid,
                        "counts": pii_res.counts,
                    }
                )
            cleaned.append(item)

        stats = GuardrailScanStats(
            scanned_count=len(chunks),
            passed_count=len(cleaned),
            masked_pii_count=masked_pii,
            dropped_acl_count=dropped_acl,
            dropped_injection_count=dropped_inj,
            events=events,
        )
        return cleaned, stats

    def filter_external_results(
        self,
        results: list[ExternalResult],
    ) -> tuple[list[ExternalResult], GuardrailScanStats]:
        """Apply the exact same PII and prompt-injection scan to external search results."""
        cleaned: list[ExternalResult] = []
        events: list[dict[str, Any]] = []
        masked_pii = dropped_inj = 0

        for res in results:
            inj_match = has_prompt_injection(res.text)
            if inj_match:
                dropped_inj += 1
                events.append(
                    {
                        "layer": "retriever",
                        "action": "block",
                        "policy": "external_prompt_injection_scan",
                        "ref_id": res.source_url,
                        "matched": inj_match,
                    }
                )
                continue

            pii_res = self._redactor.redact(res.text)
            if pii_res.contains_pii:
                masked_pii += 1
                events.append(
                    {
                        "layer": "retriever",
                        "action": "mask",
                        "policy": "external_pii_redaction",
                        "ref_id": res.source_url,
                        "counts": pii_res.counts,
                    }
                )
            cleaned.append(
                ExternalResult(
                    text=pii_res.redacted_text,
                    source_url=res.source_url,
                    retrieved_at=res.retrieved_at,
                    source_kind=res.source_kind,
                    external=True,
                )
            )

        stats = GuardrailScanStats(
            scanned_count=len(results),
            passed_count=len(cleaned),
            masked_pii_count=masked_pii,
            dropped_acl_count=0,
            dropped_injection_count=dropped_inj,
            events=events,
        )
        return cleaned, stats
