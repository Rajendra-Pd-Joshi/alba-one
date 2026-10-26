"""Stage telemetry recorder for latency, token cost (`llm_calls`), and LangSmith spans (`retrieval/telemetry.py`)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any

from alba_one.core.pricing import calculate_llm_cost_usd


@dataclass(frozen=True)
class StageTelemetryRecord:
    """Telemetry record aligned with the `llm_calls` table and LangSmith trace spans."""

    call_id: str
    tenant_id: str
    stage: str
    model: str
    prompt_version: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool = False
    langsmith_span_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalTelemetryCollector:
    """Collects per-stage `llm_calls` telemetry and LangSmith span metadata during a pipeline run."""

    def __init__(
        self,
        *,
        tenant_id: str,
        prices_by_model: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.prices = prices_by_model or {
            "gpt-4o-2024-08-06": {"input_per_1m": 2.5, "output_per_1m": 10.0},
            "rerank-v4.0-pro": {"input_per_1m": 2.0, "output_per_1m": 0.0},
            "text-embedding-3-large": {"input_per_1m": 0.13, "output_per_1m": 0.0},
        }
        self.records: list[StageTelemetryRecord] = []

    def record_stage(
        self,
        *,
        stage: str,
        model: str,
        prompt_version: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> StageTelemetryRecord:
        """Record a completed retrieval pipeline stage with calculated USD cost."""
        cost = 0.0
        if model in self.prices and (prompt_tokens > 0 or completion_tokens > 0):
            cost = calculate_llm_cost_usd(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                prices_by_model=self.prices,
            )
        rec = StageTelemetryRecord(
            call_id=f"llm_{uuid.uuid4().hex[:12]}",
            tenant_id=self.tenant_id,
            stage=stage,
            model=model,
            prompt_version=prompt_version,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            langsmith_span_name=f"alba_one.retrieval.{stage}",
            metadata=dict(metadata or {}),
        )
        self.records.append(rec)
        return rec

    @contextmanager
    def measure(
        self,
        stage: str,
        *,
        model: str = "deterministic",
        prompt_version: str = "v1.0",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        """Context manager timing a stage and recording its `StageTelemetryRecord`."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.record_stage(
                stage=stage,
                model=model,
                prompt_version=prompt_version,
                latency_ms=elapsed_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                metadata=metadata,
            )

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return all collected stage telemetry records as JSON-serializable dicts."""
        return [asdict(r) for r in self.records]
