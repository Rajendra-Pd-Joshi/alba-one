# ADR 0003: Self-Hosted Mem0 Vector Store Selection (`pgvector` on PostgreSQL vs. Qdrant)

- **Status:** Accepted (Phase 4 — Guardrails, Memory, and Operational Controls)
- **Date:** 2026-10-24
- **Owners:** ALBACONNECT Engineering

## Context
ALBA ONE uses the open-source self-hosted `mem0ai` library (`Memory.from_config(...)`) for long-term memory (`MEMORY_PROVIDER=mem0`), with `langmem` and `in_memory` supported behind the same `LongTermMemoryPort` interface. All write policies, PII/secret scrubbing, tenant/user scoping (`tenant_id`, `user_id`, `team_id`), TTL expiration, and conflict resolution live in `MemoryService` above the adapters.

Self-hosted `mem0ai` requires:
1. An LLM for fact extraction and conflict resolution -> routed through our `GATEWAY_BASE_URL` (`MAIN_MODEL`).
2. An embedder -> routed through our `GATEWAY_BASE_URL` (`EMBEDDING_MODEL` / `text-embedding-3-large`).
3. A vector store under our infrastructure control (`pgvector` on PostgreSQL vs. a dedicated Qdrant cluster).

## Comparison

| Criterion | **`pgvector` on Application PostgreSQL (Selected)** | **Standalone Qdrant Cluster** |
| :--- | :--- | :--- |
| **Operational Simplicity (Principle 11)** | Reuses the existing PostgreSQL 16 instance, backup/PITR pipeline, and VPC security groups | Adds a separate stateful distributed database to deploy, patch, back up, and monitor |
| **Tenant & User Metadata Filtering** | Native SQL indexing on `(tenant_id, user_id, team_id)` in the `mem0_memories` table | Payload filtering in Qdrant collections |
| **Scale Profile for Long-Term Memory** | Per-user/team approved decision rationales and preferences total $10^3 - 10^6$ vectors per tenant—well within `pgvector` HNSW sweet spot | Designed for $10^7+$ vectors; unnecessary overhead for curated memory records |

## Decision
We select **`pgvector` on our controlled PostgreSQL 16 instance** (`provider: "pgvector"` in `Mem0OSSAdapter.build_mem0_config()`) as the default vector store for self-hosted `mem0ai`, and route both Mem0's `llm` and `embedder` blocks through `GATEWAY_BASE_URL`.
