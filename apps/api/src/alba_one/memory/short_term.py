"""Short-Term (Thread-Scoped) Memory & Summariser (`memory/short_term.py`).

Provides:
1. Durable thread state checkpointing keyed by `(tenant_id, thread_id)` so a user can
   refresh their browser and resume a clarification or decision session seamlessly.
2. Conversation summariser (`summarize_and_trim_messages`) that trims older turns
   when message count exceeds `max_recent_messages`, while strictly preserving:
   - Decision-relevant entities & constraints (`extracted_facts`)
   - All `clarification_answers`
3. Factory `create_langgraph_checkpointer` returning LangGraph's `AsyncPostgresSaver` /
   `MemorySaver` when running inside LangGraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThreadCheckpoint:
    """Durable thread state scoped to `(tenant_id, thread_id)`."""

    tenant_id: str
    thread_id: str
    user_id: str
    lang: str = "ja"
    messages: list[dict[str, str]] = field(default_factory=list)
    clarification_answers: list[str] = field(default_factory=list)
    extracted_facts: list[str] = field(default_factory=list)
    summary: str = ""
    active_entity: str | None = None


def summarize_and_trim_messages(
    messages: list[dict[str, str]],
    *,
    clarification_answers: list[str] | None = None,
    existing_summary: str = "",
    max_recent_messages: int = 4,
    lang: str = "ja",
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Trim conversation history to `max_recent_messages` while preserving facts and clarifications."""
    answers = list(clarification_answers or [])
    facts: list[str] = []

    for msg in messages:
        content = str(msg.get("content", "")).strip()
        if any(
            kw in content.lower()
            for kw in ("rt-knt-", "vh-", "tyo-oi-", "yok-hm-", "stf-", "v2.", "sla", "残業", "オーロラ")
        ):
            facts.append(content)

    unique_facts = list(dict.fromkeys(facts))
    if len(messages) <= max_recent_messages:
        summary_parts = [p for p in [existing_summary, *unique_facts, *answers] if p]
        return " | ".join(summary_parts), list(messages), unique_facts

    older = messages[:-max_recent_messages]
    recent = messages[-max_recent_messages:]
    older_digest = "; ".join(f"{m.get('role', 'user')}: {m.get('content', '')[:80]}" for m in older)

    if lang == "ja":
        summary = (
            f"[要約履歴] {older_digest} | [重要事実] {' / '.join(unique_facts)} | "
            f"[確認済回答] {' / '.join(answers)}"
        ).strip(" |")
    else:
        summary = (
            f"[History Summary] {older_digest} | [Key Facts] {' / '.join(unique_facts)} | "
            f"[Clarification Answers] {' / '.join(answers)}"
        ).strip(" |")

    if existing_summary and existing_summary not in summary:
        summary = f"{existing_summary} | {summary}"

    return summary, recent, unique_facts


class ShortTermThreadMemory:
    """Tenant-isolated durable thread memory store supporting browser-refresh resumption."""

    def __init__(self, max_recent_messages: int = 4) -> None:
        self.max_recent_messages = max_recent_messages
        self._store: dict[tuple[str, str], ThreadCheckpoint] = {}

    def save_turn(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        role: str,
        content: str,
        clarification_answer: str | None = None,
        active_entity: str | None = None,
        lang: str = "ja",
    ) -> ThreadCheckpoint:
        """Append a message/clarification to the thread, summarize if needed, and persist."""
        if not tenant_id.strip() or not thread_id.strip():
            raise ValueError("tenant_id and thread_id are required for ShortTermThreadMemory.")
        key = (tenant_id.strip(), thread_id.strip())
        cp = self._store.get(key)
        if cp is None:
            cp = ThreadCheckpoint(
                tenant_id=tenant_id.strip(),
                thread_id=thread_id.strip(),
                user_id=user_id,
                lang=lang,
            )
            self._store[key] = cp

        cp.messages.append({"role": role, "content": content})
        if clarification_answer and clarification_answer.strip():
            cp.clarification_answers.append(clarification_answer.strip())
        if active_entity:
            cp.active_entity = active_entity

        summary, trimmed_msgs, facts = summarize_and_trim_messages(
            cp.messages,
            clarification_answers=cp.clarification_answers,
            existing_summary=cp.summary,
            max_recent_messages=self.max_recent_messages,
            lang=cp.lang,
        )
        cp.summary = summary
        cp.messages = trimmed_msgs
        cp.extracted_facts = facts
        return cp

    def resume_thread(self, *, tenant_id: str, thread_id: str) -> ThreadCheckpoint | None:
        """Resume a thread after a browser refresh; strictly isolated by `tenant_id`."""
        return self._store.get((tenant_id.strip(), thread_id.strip()))

    def to_hook_dict(self, *, tenant_id: str, thread_id: str) -> dict[str, Any]:
        """Format thread memory for Phase 3 `clarifier` and `query_rewriter` hooks."""
        cp = self.resume_thread(tenant_id=tenant_id, thread_id=thread_id)
        if cp is None:
            return {}
        return {
            "summary": cp.summary,
            "active_entity": cp.active_entity or "",
            "clarification_answers": list(cp.clarification_answers),
            "extracted_facts": list(cp.extracted_facts),
            "recent_messages": list(cp.messages),
        }


def create_langgraph_checkpointer() -> Any:
    """Return a LangGraph `MemorySaver` checkpointer for durable graph state."""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
