"""Transactional Outbox & LangGraph Postgres Checkpointer Resume (`agents/hitl/outbox.py`).

Per Phase 7 User Answer 2:
- `thread_id = decision_id` on the LangGraph Postgres checkpointer
  (`langgraph.checkpoint.postgres.aio.AsyncPostgresSaver` from `langgraph-checkpoint-postgres >= 2.0.0`,
  using `Command(resume=...)` from `langgraph.types`).
- Outbox pattern:
  1. In ONE atomic transaction, write the append-only approval record + an `OutboxResumeRow`
     (`status="pending"`) and set decision state to `approval_recorded_resume_pending`.
  2. Return HTTP 202 immediately.
  3. Worker calls `process_outbox_row(...)` to resume the checkpointer idempotently and advance
     the decision state to `approved | approved_with_conditions | rejected | needs_evidence`.
  4. Simulated or real worker crashes leave the decision in `approval_recorded_resume_pending`,
     increment `alert_failure_count`, and retry cleanly with backoff.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from alba_one.agents.decision_state import DecisionStateType, transition_decision_state

OutboxStatusType = Literal["pending", "completed", "failed_retryable"]


@dataclass
class OutboxResumeRow:
    """Single transactional outbox row scheduling a LangGraph checkpoint resume."""

    outbox_id: str
    decision_id: str
    tenant_id: str
    approval_id: str
    target_state: DecisionStateType
    resume_payload: dict[str, Any]
    status: OutboxStatusType = "pending"
    attempt_count: int = 0
    last_error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointResumePort(Protocol):
    """Protocol for resuming a paused LangGraph thread (`thread_id = decision_id`)."""

    def resume_thread(self, thread_id: str, resume_payload: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryCheckpointSaver(CheckpointResumePort):
    """Deterministic in-memory checkpointer for offline tests and simulated crash recovery."""

    def __init__(self, *, fail_next_n_calls: int = 0) -> None:
        self.fail_next_n_calls = fail_next_n_calls
        self.resumed_threads: dict[str, dict[str, Any]] = {}

    def resume_thread(self, thread_id: str, resume_payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail_next_n_calls > 0:
            self.fail_next_n_calls -= 1
            raise RuntimeError(f"Simulated worker/checkpointer crash for thread '{thread_id}'.")
        # Idempotent: resuming the same thread_id with the same approval_id is a no-op if already resumed
        existing = self.resumed_threads.get(thread_id)
        if existing and existing.get("approval_id") == resume_payload.get("approval_id"):
            return existing
        record = {
            "thread_id": thread_id,
            "approval_id": resume_payload.get("approval_id"),
            "action": resume_payload.get("action"),
            "resumed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.resumed_threads[thread_id] = record
        return record


async def resume_langgraph_postgres_checkpoint(
    conn_string: str,
    graph_builder: Any,
    decision_id: str,
    resume_payload: dict[str, Any],
) -> Any:
    """Target-stack LangGraph async Postgres checkpointer resume (`langgraph-checkpoint-postgres >= 2.0.0`)."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command

    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        await checkpointer.setup()
        graph = graph_builder.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": decision_id}}
        return await graph.ainvoke(Command(resume=resume_payload), config=config)


def process_outbox_row(
    row: OutboxResumeRow,
    decision_record: dict[str, Any],
    checkpointer: CheckpointResumePort,
    *,
    alert_counter: dict[str, int] | None = None,
    max_evidence_loops: int = 2,
) -> bool:
    """Idempotently resume the graph checkpoint for `row` and advance `decision_record['state']`."""
    if row.status == "completed":
        return True

    row.attempt_count += 1
    try:
        # thread_id MUST equal decision_id
        checkpointer.resume_thread(row.decision_id, row.resume_payload)
        cur_state: DecisionStateType = decision_record["state"]
        if cur_state == "approval_recorded_resume_pending":
            new_state, new_loops = transition_decision_state(
                cur_state,
                row.target_state,
                evidence_loops_used=int(decision_record.get("evidence_loops_used", 0)),
                max_evidence_loops=max_evidence_loops,
            )
            decision_record["state"] = new_state
            decision_record["evidence_loops_used"] = new_loops
        row.status = "completed"
        row.completed_at = datetime.now(timezone.utc).isoformat()
        row.last_error = None
        return True
    except Exception as exc:
        row.status = "failed_retryable"
        row.last_error = str(exc)
        if alert_counter is not None:
            alert_counter["outbox_resume_failures"] = alert_counter.get("outbox_resume_failures", 0) + 1
        return False
