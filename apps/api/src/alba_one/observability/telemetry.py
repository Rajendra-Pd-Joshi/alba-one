"""Bounded Async/Batched Span Telemetry Recorder & LangSmith Exporter (`observability/telemetry.py`).

Per Phase 9 User Answer 1:
- Writing spans must NEVER break or slow a request.
- Uses a bounded queue (`max_queue_size`). On overflow, drops low-priority spans (`kind in ('calc', 'guardrail')`
  or incoming non-error spans) and increments `spans_dropped` (exposed in `/api/v1/health`).
- DB write failures (`db_write_failures`) and LangSmith export failures (`langsmith_export_failures`)
  are caught, logged, and counted — never raised!
- Applies LangSmith input/output redaction (`hide_inputs=True, hide_outputs=True`) when
  `TRACE_CAPTURE_CONTENT=false` and tags runs with `tenant_id` and `decision_id`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any
import uuid

from alba_one.observability.cost import PriceTableConfig, compute_call_cost, load_price_table, resolve_tokens
from alba_one.observability.spans import (
    PhaseStepType,
    SpanKindType,
    SpanRecord,
    SpanStatusType,
    is_trace_capture_enabled,
    scrub_span_text,
)


class BoundedSpanTelemetryRecorder:
    """Resilient, non-blocking telemetry recorder with bounded queue, DB sink, and optional LangSmith exporter."""

    def __init__(
        self,
        *,
        max_queue_size: int = 1000,
        capture_content: bool | None = None,
        price_table: PriceTableConfig | None = None,
        db_writer: Callable[[list[SpanRecord]], None] | None = None,
        langsmith_exporter: Callable[[SpanRecord, dict[str, Any]], None] | None = None,
    ) -> None:
        self.max_queue_size = max(1, max_queue_size)
        self.capture_content = is_trace_capture_enabled(capture_content)
        self.price_table = price_table or load_price_table()
        self._db_writer = db_writer
        self._langsmith_exporter = langsmith_exporter

        self.queue: deque[SpanRecord] = deque()
        self.flushed_spans: list[SpanRecord] = []
        self.spans_dropped: int = 0
        self.db_write_failures: int = 0
        self.langsmith_export_failures: int = 0

    def record_span(
        self,
        *,
        trace_id: str,
        tenant_id: str,
        run_id: str,
        phase_step: PhaseStepType,
        kind: SpanKindType,
        model_or_tool: str,
        provider: str,
        latency_ms: float,
        status: SpanStatusType = "ok",
        decision_id: str | None = None,
        parent_span_id: str | None = None,
        attempt: int = 1,
        retry_count: int = 0,
        cache_hit: bool = False,
        reported_tokens_in: int | None = None,
        reported_tokens_out: int | None = None,
        prompt_text: str | None = None,
        output_text: str | None = None,
        prompt_version: str | None = None,
        guardrail_version: str | None = None,
        model_config_version: str | None = "1.0",
        tool_def_hash: str | None = None,
        app_version: str = "0.9.0",
        lang: str = "ja",
        ttfb_ms: float | None = None,
        error_type: str | None = None,
    ) -> SpanRecord | None:
        """Create a sanitized `SpanRecord` and enqueue it without ever raising an exception."""
        try:
            tok_in, tok_out, tok_est = resolve_tokens(
                reported_tokens_in=reported_tokens_in,
                reported_tokens_out=reported_tokens_out,
                prompt_text=prompt_text,
                output_text=output_text,
            )
            is_cached = cache_hit or status == "cache_hit"
            cost_amt, cost_cur, pt_ver, cost_est = compute_call_cost(
                model_or_tool=model_or_tool,
                tokens_in=tok_in,
                tokens_out=tok_out,
                cache_hit=is_cached,
                tokens_estimated=tok_est,
                price_table=self.price_table,
            )
            p_hash, p_bytes, p_redacted = scrub_span_text(prompt_text, capture_content=self.capture_content)
            o_hash, o_bytes, o_redacted = scrub_span_text(output_text, capture_content=self.capture_content)

            span = SpanRecord(
                span_id=f"sp_{uuid.uuid4().hex[:12]}",
                parent_span_id=parent_span_id,
                trace_id=trace_id,
                tenant_id=tenant_id,
                decision_id=decision_id,
                run_id=run_id,
                attempt=attempt,
                phase_step=phase_step,
                kind=kind,
                model_or_tool=model_or_tool,
                provider=provider,
                prompt_version=prompt_version,
                guardrail_version=guardrail_version,
                model_config_version=model_config_version,
                tool_def_hash=tool_def_hash,
                app_version=app_version,
                lang=lang,
                tokens_in=tok_in,
                tokens_out=tok_out,
                tokens_estimated=tok_est,
                latency_ms=round(float(latency_ms), 2),
                ttfb_ms=ttfb_ms,
                status="cache_hit" if is_cached else status,
                error_type=error_type,
                retry_count=retry_count,
                cache_hit=is_cached,
                cost_amount=cost_amt,
                cost_currency=cost_cur,
                price_table_version=pt_ver,
                cost_estimated=cost_est,
                prompt_hash=p_hash,
                prompt_bytes=p_bytes,
                output_hash=o_hash,
                output_bytes=o_bytes,
                captured_prompt_redacted=p_redacted,
                captured_output_redacted=o_redacted,
            )
            self._enqueue_bounded(span)
            self._export_to_langsmith_safely(span)
            return span
        except Exception:
            self.spans_dropped += 1
            return None

    def _enqueue_bounded(self, span: SpanRecord) -> None:
        if len(self.queue) >= self.max_queue_size:
            # Drop low-priority span (e.g. calc or cache_hit) to preserve error/LLM/tool spans
            low_idx = next(
                (i for i, s in enumerate(self.queue) if s.kind in ("calc", "guardrail") or s.cache_hit),
                None,
            )
            if low_idx is not None:
                del self.queue[low_idx]
                self.spans_dropped += 1
                self.queue.append(span)
            else:
                self.spans_dropped += 1
            return
        self.queue.append(span)

    def _export_to_langsmith_safely(self, span: SpanRecord) -> None:
        if self._langsmith_exporter is None:
            return
        try:
            ls_meta = {
                "tags": [f"tenant:{span.tenant_id}", f"decision:{span.decision_id or 'none'}"],
                "hide_inputs": not self.capture_content,
                "hide_outputs": not self.capture_content,
            }
            self._langsmith_exporter(span, ls_meta)
        except Exception:
            self.langsmith_export_failures += 1

    def flush(self, batch_size: int = 200) -> int:
        """Flush queued spans to PostgreSQL (or in-memory store); never raises on DB failure."""
        batch: list[SpanRecord] = []
        while self.queue and len(batch) < batch_size:
            batch.append(self.queue.popleft())
        if not batch:
            return 0
        try:
            if self._db_writer is not None:
                self._db_writer(batch)
            self.flushed_spans.extend(batch)
            return len(batch)
        except Exception:
            self.db_write_failures += 1
            return 0

    def health_counters(self) -> dict[str, int]:
        return {
            "queue_depth": len(self.queue),
            "flushed_count": len(self.flushed_spans),
            "spans_dropped": self.spans_dropped,
            "db_write_failures": self.db_write_failures,
            "langsmith_export_failures": self.langsmith_export_failures,
        }
