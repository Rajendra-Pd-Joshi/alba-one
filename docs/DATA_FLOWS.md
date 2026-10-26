# ALBA ONE — Data Flows & Trust Boundaries (`docs/DATA_FLOWS.md`)

## 1. Cross-Boundary Data Flow Diagram (Mermaid)

```mermaid
flowchart LR
    subgraph OnPrem["On-Premise / Private Tenant Boundary (Japan)"]
        OP_PG[("On-Prem PostgreSQL\nRead-Only Views (v_kb_*)\n+ kb_documents & kb_chunks (Full Text)")]
        PII["Local Deterministic PII Redactor\n(MyNumber, JP Phone, Postal, Names, Secrets)"]
        LOCAL_GR["Local Deterministic Guardrails\n(ACL, SQL Guard, SSRF, JP Word Filter, Budgets)"]
    end

    subgraph AppVPC["ALBA ONE Application Plane (ap-northeast-1 Tokyo)"]
        API["FastAPI + LangGraph Core Loop"]
        REDIS[("Redis 7.4\nExact LLM Cache + Lua Rate Limiter\n+ Thread Checkpointer")]
        MEM_SVC["MemoryService Policy Gate\n(Requires Approval/Confirmation + PII Scrub)"]
        MEM0[("Self-Hosted Mem0 OSS\n+ pgvector on App Postgres")]
    end

    subgraph CloudProviders["External Cloud & AI Providers (TLS 1.3)"]
        BEDROCK["AWS Bedrock Guardrails (Standard Tier)\nProfile: apac.guardrail.v1:0\n(Tokyo, Osaka, Seoul, Singapore, Sydney, Mumbai)"]
        GW["LLM Gateway (Portkey / Bifrost / TensorZero / Mesh)"]
        OPENAI["OpenAI (text-embedding-3-large & MAIN_MODEL)"]
        COHERE["Cohere v2 Rerank (rerank-v4.0-pro)"]
        PINECONE[("Pinecone Vector Index\nMetadata ONLY — NO Chunk Text")]
    end

    OP_PG -->|"1. Extract rows"| PII
    PII -->|"2. Redacted chunk text"| API
    API -->|"3. Upsert vectors + 7 metadata keys (NO text)"| PINECONE
    API <-->|"4. Parallel ApplyGuardrail (INPUT/OUTPUT)\n[APAC Cross-Region]"| BEDROCK
    API <-->|"5. Parallel Local Checks"| LOCAL_GR
    API -->|"6. Redacted query + candidate chunks"| COHERE
    API -->|"7. Redacted prompt + cited chunks + headers"| GW --> OPENAI
    API -->|"8. Approved / User-Confirmed Facts"| MEM_SVC
    MEM_SVC -->|"9. PII-Scrubbed Memory"| MEM0
    MEM0 -->|"10. Fact Extraction & Embedding via Gateway"| GW
    API <--> REDIS
```

## 2. Boundary Crossing Inventory Table

| Data Crossing Boundary | Source -> Destination | Leaves Japan (`ap-northeast-1`)? | Encryption | Retention | PII & Safety Controls Applied Before Crossing |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Vector Embeddings & Metadata** | On-Prem Indexer -> Pinecone (`namespace=tenant_id`) | Yes (Pinecone cloud region) | TLS 1.3 in transit; AES-256 at rest | Until chunk deleted/re-indexed | **No chunk text is sent to Pinecone** (`assert_pinecone_metadata_safe`). Only `chunk_id, tenant_id, acl_tags, entity_type, lang, valid_from, valid_to`. |
| **2. Chunk & Query Text for Embedding** | Indexer / Retriever -> LLM Gateway -> OpenAI (`text-embedding-3-large`) | Yes (Provider endpoint) | TLS 1.3 | Zero data retention (enterprise API policy) | `PIIRedactor` scrubs My Number, JP phones, `〒` postal codes, emails, and configured names on-premise first. |
| **3. Guardrail Evaluation Payloads** | API (`guardrails/bedrock.py`) -> AWS Bedrock (`ApplyGuardrail` with `apac.guardrail.v1:0`) | **Yes — APAC Cross-Region** (`ap-northeast-1/2/3`, `ap-south-1`, `ap-southeast-1/2`) | AWS internal TLS 1.3 | Stateless API call (not stored by Bedrock) | Local `PIIRedactor` and secret linter run in parallel; sensitive fields masked before downstream persistence. |
| **4. Candidate Chunks for Reranking** | Retriever (`reranker.py`) -> Cohere v2 (`/v2/rerank`) or Gateway | Yes (Provider endpoint) | TLS 1.3 | Stateless API call | Retriever guardrail drops ACL-unauthorized and prompt-injected chunks and masks PII before reranking. |
| **5. Prompts, Retrieved Chunks & Tool Summaries** | Agents / Judge / Mem0 OSS -> LLM Gateway -> LLM Provider | Yes (Provider endpoint) | TLS 1.3 | Gateway audit log + zero provider training retention | 7-layer guardrails (Prompt, Input, Retriever, Tool, Output, HITL, Ops) + pre-Mem0 PII scrubbing in `MemoryService`. |
