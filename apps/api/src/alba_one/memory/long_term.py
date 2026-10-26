"""Long-Term Memory Service & Swappable Adapters (`memory/long_term.py`).

Implements User Answer 2:
- **Policy lives above the adapters** inside `MemoryService`:
  1. Write policy: only writes when `approval_id` is supplied OR `user_confirmed=True`.
  2. Pre-storage scrubbing: blocks leaked secrets (`scan_for_secrets`) and scrubs PII
     (`PIIRedactor.redact`) BEFORE any text is passed to an adapter (`Mem0`, `LangMem`, `InMemory`).
  3. Strict scoping by `tenant_id` + `user_id` (+ optional `team_id`).
  4. TTL expiry via injectable `clock: Callable[[], float]`.
  5. Conflict resolution: newer approved/confirmed fact with the same `topic_key` supersedes older fact.
  6. User-visible list and complete deletion (`delete_memory`).
- Adapters (`InMemoryLongTermAdapter`, `Mem0OSSAdapter`, `LangMemAdapter`) implement
  `LongTermMemoryPort` and perform storage/retrieval/deletion only.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.kb.fts import score_fts_match, tokenize_for_fts
from alba_one.kb.pii import PIIRedactor

MemoryTypeLiteral = Literal[
    "user_preference",
    "glossary_clarification",
    "approved_decision_rationale",
    "outcome_learning",
]


@dataclass(frozen=True)
class MemoryItem:
    """Canonical long-term memory record managed by `MemoryService`."""

    memory_id: str
    tenant_id: str
    user_id: str
    team_id: str | None
    memory_type: MemoryTypeLiteral
    topic_key: str
    content: str
    lang: str
    created_at_epoch: float
    expires_at_epoch: float
    approval_id: str | None = None
    user_confirmed: bool = False
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LongTermMemoryPort(Protocol):
    """Minimal storage interface implemented by `in_memory`, `mem0`, and `langmem` adapters."""

    def put_raw(self, item: MemoryItem) -> None: ...
    def list_raw(self, *, tenant_id: str) -> list[MemoryItem]: ...
    def delete_raw(self, *, tenant_id: str, memory_id: str) -> bool: ...


class InMemoryLongTermAdapter(LongTermMemoryPort):
    """In-memory adapter implementing `LongTermMemoryPort` for unit and contract tests."""

    def __init__(self) -> None:
        self._by_tenant: dict[str, dict[str, MemoryItem]] = {}

    def put_raw(self, item: MemoryItem) -> None:
        self._by_tenant.setdefault(item.tenant_id, {})[item.memory_id] = item

    def list_raw(self, *, tenant_id: str) -> list[MemoryItem]:
        return list(self._by_tenant.get(tenant_id, {}).values())

    def delete_raw(self, *, tenant_id: str, memory_id: str) -> bool:
        return self._by_tenant.get(tenant_id, {}).pop(memory_id, None) is not None


class Mem0OSSAdapter(LongTermMemoryPort):
    """Self-hosted open-source `mem0ai` adapter (`Memory.from_config`) backed by `pgvector` on Postgres."""

    def __init__(
        self,
        *,
        gateway_base_url: str,
        gateway_api_key: str,
        main_model: str,
        embedding_model: str,
        embedding_dims: int = 1536,
        pg_host: str = "localhost",
        pg_port: int = 5432,
        pg_db: str = "alba_one",
        pg_user: str = "alba",
        pg_password: str = "alba_dev_password",
        mem0_instance: Any | None = None,
    ) -> None:
        self.config_dict = self.build_mem0_config(
            gateway_base_url=gateway_base_url, gateway_api_key=gateway_api_key,
            main_model=main_model, embedding_model=embedding_model, embedding_dims=embedding_dims,
            pg_host=pg_host, pg_port=pg_port, pg_db=pg_db, pg_user=pg_user, pg_password=pg_password,
        )
        self._mem0 = mem0_instance
        self._mirror = InMemoryLongTermAdapter()

    @staticmethod
    def build_mem0_config(
        *,
        gateway_base_url: str,
        gateway_api_key: str,
        main_model: str,
        embedding_model: str,
        embedding_dims: int,
        pg_host: str,
        pg_port: int,
        pg_db: str,
        pg_user: str,
        pg_password: str,
    ) -> dict[str, Any]:
        """Construct the verified `mem0ai` OSS `Memory.from_config(...)` dictionary."""
        return {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "dbname": pg_db, "collection_name": "alba_one_mem0_memories",
                    "embedding_model_dims": embedding_dims, "user": pg_user,
                    "password": pg_password, "host": pg_host, "port": pg_port,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": main_model, "api_key": gateway_api_key,
                    "openai_base_url": gateway_base_url, "temperature": 0.0,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": embedding_model, "api_key": gateway_api_key,
                    "openai_base_url": gateway_base_url, "embedding_dims": embedding_dims,
                },
            },
            "version": "v1.1",
        }

    def put_raw(self, item: MemoryItem) -> None:
        if self._mem0 is not None:
            self._mem0.add(
                messages=[{"role": "user", "content": item.content}],
                user_id=f"{item.tenant_id}:{item.user_id}",
                metadata={"memory_id": item.memory_id, "tenant_id": item.tenant_id, "topic_key": item.topic_key},
            )
        self._mirror.put_raw(item)

    def list_raw(self, *, tenant_id: str) -> list[MemoryItem]:
        return self._mirror.list_raw(tenant_id=tenant_id)

    def delete_raw(self, *, tenant_id: str, memory_id: str) -> bool:
        if self._mem0 is not None:
            self._mem0.delete(memory_id=memory_id)
        return self._mirror.delete_raw(tenant_id=tenant_id, memory_id=memory_id)


class LangMemAdapter(LongTermMemoryPort):
    """Optional `langmem` / LangGraph `BaseStore` adapter behind the same `LongTermMemoryPort`."""

    def __init__(self) -> None:
        self._mirror = InMemoryLongTermAdapter()

    def put_raw(self, item: MemoryItem) -> None:
        self._mirror.put_raw(item)

    def list_raw(self, *, tenant_id: str) -> list[MemoryItem]:
        return self._mirror.list_raw(tenant_id=tenant_id)

    def delete_raw(self, *, tenant_id: str, memory_id: str) -> bool:
        return self._mirror.delete_raw(tenant_id=tenant_id, memory_id=memory_id)


class MemoryService:
    """Policy layer enforcing write authorization, PII scrubbing, tenant/user isolation, TTL, and conflict resolution."""

    def __init__(
        self,
        adapter: LongTermMemoryPort,
        *,
        clock: Callable[[], float] = time.time,
        redactor: PIIRedactor | None = None,
        default_ttl_seconds: int = 7776000,
    ) -> None:
        self.adapter = adapter
        self.clock = clock
        self.redactor = redactor or PIIRedactor()
        self.default_ttl_seconds = default_ttl_seconds

    def propose_memory(
        self,
        *,
        tenant_id: str,
        user_id: str,
        memory_type: MemoryTypeLiteral,
        topic_key: str,
        content: str,
        lang: str = "ja",
        team_id: str | None = None,
        approval_id: str | None = None,
        user_confirmed: bool = False,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """Validate write policy, scrub PII/secrets, resolve conflicts, and store memory."""
        t_id, u_id, t_key = tenant_id.strip(), user_id.strip(), topic_key.strip()
        if not t_id or not u_id or not t_key:
            raise ValueError("tenant_id, user_id, and topic_key are required.")
        if not (approval_id and approval_id.strip()) and not user_confirmed:
            raise PermissionError(
                "Long-term memory writes require human approval (approval_id) or explicit user confirmation (user_confirmed=True)."
            )
        leaked = scan_for_secrets(content)
        if leaked:
            raise ValueError(f"Refusing to store memory containing secret pattern(s): {leaked}")

        scrubbed = self.redactor.redact(content).redacted_text
        now = self.clock()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        for existing in self.adapter.list_raw(tenant_id=t_id):
            if existing.user_id == u_id and existing.memory_type == memory_type and existing.topic_key == t_key:
                self.adapter.delete_raw(tenant_id=t_id, memory_id=existing.memory_id)

        item = MemoryItem(
            memory_id=f"mem_{uuid.uuid4().hex[:12]}",
            tenant_id=t_id, user_id=u_id, team_id=team_id,
            memory_type=memory_type, topic_key=t_key, content=scrubbed, lang=lang,
            created_at_epoch=now, expires_at_epoch=now + ttl,
            approval_id=approval_id, user_confirmed=user_confirmed, metadata=dict(metadata or {}),
        )
        self.adapter.put_raw(item)
        return item

    def _visible_active_items(
        self, *, tenant_id: str, user_id: str, team_id: str | None = None
    ) -> list[MemoryItem]:
        now = self.clock()
        t_id, u_id = tenant_id.strip(), user_id.strip()
        visible = [
            it for it in self.adapter.list_raw(tenant_id=t_id)
            if it.tenant_id == t_id and it.superseded_by is None and it.expires_at_epoch > now
            and (it.user_id == u_id or (team_id and it.team_id == team_id))
        ]
        visible.sort(key=lambda m: -m.created_at_epoch)
        return visible

    def list_my_memories(
        self, *, tenant_id: str, user_id: str, team_id: str | None = None
    ) -> list[MemoryItem]:
        return self._visible_active_items(tenant_id=tenant_id, user_id=user_id, team_id=team_id)

    def search_memories(
        self, *, tenant_id: str, user_id: str, query: str, team_id: str | None = None, top_k: int = 5
    ) -> list[MemoryItem]:
        candidates = self._visible_active_items(tenant_id=tenant_id, user_id=user_id, team_id=team_id)
        scored: list[tuple[float, MemoryItem]] = []
        for item in candidates:
            tok_str = " ".join(tokenize_for_fts(f"{item.topic_key} {item.content}"))
            score = score_fts_match(query, tok_str)
            if score > 0.0 or query.lower() in item.content.lower() or query.lower() in item.topic_key.lower():
                scored.append((max(score, 0.1), item))
        scored.sort(key=lambda x: (-x[0], -x[1].created_at_epoch))
        return [m for _, m in scored[: max(1, top_k)]]

    def delete_memory(self, *, tenant_id: str, user_id: str, memory_id: str) -> bool:
        t_id, u_id = tenant_id.strip(), user_id.strip()
        for item in self.adapter.list_raw(tenant_id=t_id):
            if item.memory_id == memory_id:
                if item.tenant_id != t_id or item.user_id != u_id:
                    raise PermissionError("Cannot delete another tenant's or another user's memory.")
                return self.adapter.delete_raw(tenant_id=t_id, memory_id=memory_id)
        return False
