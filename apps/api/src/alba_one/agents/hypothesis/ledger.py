"""Run-Scoped Evidence Ledger & Tool Call Deduplicator (`agents/hypothesis/ledger.py`).

Per Phase 6 User Answer 1 & Phase 7 User Answer 3:
- One evidence ledger per run: every KB chunk, tool result, calculator result, external
  result, and past decision lesson gets a run-scoped ID assigned BY OUR CODE (`ev_001`...).
- Retrieved lessons (`origin="decision_asset"`) are labelled `source_type="past_decision_lesson"`
  and rendered as `"past decision lesson (context only, not verified fact)"` in prompts and UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Literal

LedgerSourceType = Literal[
    "kb_chunk",
    "tool_result",
    "calculator_result",
    "external_result",
    "past_decision_lesson",
]


@dataclass(frozen=True)
class EvidenceLedgerItem:
    """Single immutable evidence entry registered in a run's `EvidenceLedger`."""

    evidence_id: str
    tenant_id: str
    source_type: LedgerSourceType
    source_id: str
    tool_call_id: str | None
    url: str | None
    retrieved_at: str
    external: bool
    raw_text: str
    structured_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GapRecord:
    """Explicit gap recorded when a tool call fails, times out, or returns `insufficient_data`."""

    gap_id: str
    round_num: int
    mcp_server: str
    tool_name: str
    reason: str
    is_counter_evidence_query: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceLedger:
    """Run-scoped ledger assigning `ev_001..ev_NNN` IDs and deduplicating tool calls."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self._items: dict[str, EvidenceLedgerItem] = {}
        self._call_cache: dict[str, str] = {}
        self.gaps: list[GapRecord] = []
        self.budget_exhausted: bool = False
        self.budget_exhausted_reason: str | None = None
        self.total_tool_calls: int = 0
        self.round1_calls: int = 0
        self.round2_calls: int = 0
        self.accumulated_cost_usd: float = 0.0

    def _next_id(self) -> str:
        idx = len(self._items) + 1
        return f"ev_{idx:03d}"

    @staticmethod
    def canonical_call_key(mcp_server: str, tool_name: str, arguments: dict[str, Any]) -> str:
        norm_args = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        return f"{mcp_server}:{tool_name}:{norm_args}"

    def find_cached_call(self, mcp_server: str, tool_name: str, arguments: dict[str, Any]) -> EvidenceLedgerItem | None:
        key = self.canonical_call_key(mcp_server, tool_name, arguments)
        ev_id = self._call_cache.get(key)
        return self._items.get(ev_id) if ev_id else None

    def register_item(
        self,
        *,
        tenant_id: str,
        source_type: LedgerSourceType,
        source_id: str,
        raw_text: str,
        structured_data: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
        url: str | None = None,
        retrieved_at: str | None = None,
        external: bool = False,
        dedup_key: str | None = None,
    ) -> EvidenceLedgerItem:
        ev_id = self._next_id()
        now_iso = retrieved_at or datetime.now(timezone.utc).isoformat()
        item = EvidenceLedgerItem(
            evidence_id=ev_id,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            tool_call_id=tool_call_id,
            url=url,
            retrieved_at=now_iso,
            external=external,
            raw_text=raw_text,
            structured_data=structured_data or {},
        )
        self._items[ev_id] = item
        if dedup_key:
            self._call_cache[dedup_key] = ev_id
        return item

    def add_kb_chunk(
        self,
        *,
        chunk_id: str,
        text: str,
        tenant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceLedgerItem:
        """Register an on-prem KB chunk (or `past_decision_lesson` if `origin=='decision_asset'`)."""
        meta = dict(metadata or {})
        is_lesson = meta.get("origin") == "decision_asset"
        s_type: LedgerSourceType = "past_decision_lesson" if is_lesson else "kb_chunk"
        if is_lesson and "label" not in meta:
            meta["label"] = "past decision lesson"
        return self.register_item(
            tenant_id=tenant_id or self.tenant_id,
            source_type=s_type,
            source_id=chunk_id,
            raw_text=text,
            structured_data=meta,
            external=False,
        )

    def add_mcp_envelope(
        self,
        envelope: dict[str, Any],
        *,
        arguments: dict[str, Any],
    ) -> EvidenceLedgerItem:
        server = str(envelope["mcp_server"])
        tool = str(envelope["tool_name"])
        is_ext = bool(envelope.get("external", False))
        is_calc = tool.startswith("calculate_")
        src_type: LedgerSourceType = (
            "external_result"
            if is_ext
            else ("calculator_result" if is_calc else "tool_result")
        )
        data: dict[str, Any] = dict(envelope.get("data", {}))
        url: str | None = None
        if is_ext:
            url = data.get("source_url")
            for k in ("results", "articles", "benchmarks", "papers", "releases"):
                if not url and isinstance(data.get(k), list) and data[k]:
                    url = data[k][0].get("url") or data[k][0].get("source_url")

        raw_text = json.dumps(data, ensure_ascii=False)
        dedup_key = self.canonical_call_key(server, tool, arguments)
        item = self.register_item(
            tenant_id=str(arguments.get("tenant_id", self.tenant_id)),
            source_type=src_type,
            source_id=f"{server}.{tool}",
            tool_call_id=str(envelope.get("tool_call_id", "")),
            url=url,
            retrieved_at=str(envelope.get("audit", {}).get("created_at", "")),
            external=is_ext,
            raw_text=raw_text,
            structured_data=data,
            dedup_key=dedup_key,
        )
        if is_calc and data.get("status") in ("insufficient_data", "parameters_not_verified"):
            self.record_gap(
                round_num=1,
                mcp_server=server,
                tool_name=tool,
                reason=f"Calculator status={data.get('status')}: {data.get('warnings')}",
            )
        return item

    def record_gap(
        self,
        *,
        round_num: int,
        mcp_server: str,
        tool_name: str,
        reason: str,
        is_counter_evidence_query: bool = False,
    ) -> GapRecord:
        gap = GapRecord(
            gap_id=f"gap_{len(self.gaps) + 1:02d}",
            round_num=round_num,
            mcp_server=mcp_server,
            tool_name=tool_name,
            reason=reason,
            is_counter_evidence_query=is_counter_evidence_query,
        )
        self.gaps.append(gap)
        return gap

    def get(self, evidence_id: str) -> EvidenceLedgerItem | None:
        return self._items.get(evidence_id)

    def items(self) -> list[EvidenceLedgerItem]:
        return list(self._items.values())

    def format_for_prompt(self) -> str:
        lines = ["=== EVIDENCE LEDGER (cite ONLY these evidence_id values) ==="]
        for it in self._items.values():
            tag = " [EXTERNAL]" if it.external else ""
            if it.source_type == "past_decision_lesson":
                tag += " [PAST DECISION LESSON — context only, not verified fact]"
            lines.append(f"- {it.evidence_id}{tag} ({it.source_type}: {it.source_id}): {it.raw_text[:360]}")
        if self.gaps:
            lines.append("=== RECORDED EVIDENCE GAPS (must be acknowledged in hypotheses) ===")
            for g in self.gaps:
                lines.append(f"- {g.gap_id} ({g.mcp_server}.{g.tool_name}): {g.reason}")
        return "\n".join(lines)
