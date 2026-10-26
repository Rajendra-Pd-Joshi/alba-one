# ALBA ONE — System Architecture (`docs/ARCHITECTURE.md`)

**Product:** ALBA ONE — Enterprise Decision OS (`意思決定OS`)
**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified — ISO/IEC 27001)

## 1. Product Pillars

ALBA ONE structures enterprise decision-making around three pillars (used verbatim in UI and docs):

1. **Business meaning and data (`業務の意味とデータの接続`)**: Entities (companies, products, equipment, vessels), relationships, ACL permissions, and decision metadata extracted from operational databases.
2. **Workflow-specific decision support (`業務ごとの判断支援`)**: Delivery planning, staffing, vessel allocation, and ML model-release decisions.
3. **Outcome and knowledge operations (`結果と知識の運用`)**: Decision history, variance reasons, and business measures reviewed by accountable owners and written back to the knowledge base.

## 2. Full Planned System Diagram (Mermaid)

```mermaid
flowchart TB
    subgraph Client["Next.js App Router UI (EN / JP, Light Theme)"]
        WS["Decision Workspace\n(意思決定ワークスペース)"]
        AP["Approvals (承認 / 差し戻し)"]
        KB_UI["Knowledge Base (ナレッジベース)"]
        OUT_UI["Outcome Review (成果レビュー)"]
        QUAL_UI["Quality & Guardrails (品質・ガードレール)"]
    end

    subgraph Edge["FastAPI API Layer & Operational Controls"]
        AUTH["OIDC / JWT Tenancy Middleware\n(TenantContext + UserContext)"]
        RL["Redis Token-Bucket Rate Limiter\n(Per-Tenant / Per-User / Per-Tool Lua)"]
        HEALTH["Startup & Deep Health Probes\n(/health, /health/deep)"]
    end

    subgraph Guardrails["7-Layer Defense-in-Depth Guardrails (AWS Bedrock + Guardrails AI)"]
        G_IN["1. Prompt & 2. Input Guardrail"]
        G_RET["4. Retriever ACL & PII Guardrail"]
        G_TOOL["5. Tool Allowlist & Side-Effect Guardrail"]
        G_OUT["3. Output Citation & Toxicity Guardrail"]
        G_HITL["6. Human-in-the-Loop Gate"]
        G_OPS["7. Ops Budget & Anomaly Guardrail"]
    end

    subgraph CoreLoop["LangGraph Decision OS Core Loop"]
        ASK["Ask (DecisionRequest)"] --> CLAR["Clarify (ClarificationQuestion)"]
        CLAR --> REWRITE["Query Rewriter & Router (JP + EN)"]
        REWRITE --> RETRIEVE["Hybrid Retrieval & Cohere Rerank"]
        RETRIEVE --> HYP["Hypothesise (Support / Oppose / Neutral)"]
        HYP --> VALIDATE["Evidence Validator\n(Retry once -> 'insufficient evidence')"]
        VALIDATE --> JUDGE["Judge (DecisionRecommendation)"]
        JUDGE --> HITL["Human Approval (Approve / Reject / Edit)"]
        HITL --> OUTCOME["Outcome Review & KB Writeback"]
    end

    subgraph MCP["FastMCP Servers (Consumed via langchain-mcp-adapters)"]
        MCP_RET["kb-retrieval-mcp"]
        MCP_SQL["postgres-sql-mcp"]
        MCP_DEPT["department-org-mcp"]
        MCP_EXP["ml-experiments-mcp"]
        MCP_WEB["web-news-mcp"]
        MCP_APP["approvals-hitl-mcp"]
    end

    subgraph Gateway["OpenAI-Compatible LLM Gateway & Cache"]
        CACHE["Redis Exact-Match LLM Cache\n(Excludes HITL & Side-Effecting Calls)"]
        GW["Gateway (Portkey default / Bifrost / TensorZero / Mesh)"]
        MAIN_M["MAIN_MODEL / JUDGE_MODEL\n+ Fallback Chain"]
        EVAL_M["EVAL_JUDGE_MODEL\n(Distinct from MAIN_MODEL)"]
    end

    subgraph Data["Tenant-Isolated Data & Memory Stores (tenant_id enforced)"]
        PG[("PostgreSQL 16 + Alembic\n12 Core Tables + FTS (Sudachi/pg_bigm)")]
        PC[("Pinecone Vector Index\n(text-embedding-3-large)")]
        RD[("Redis 7.4\nCheckpointer + Cache + Rate Limits")]
        MEM0[("Mem0 Long-Term Memory")]
    end

    subgraph ObsEval["Observability, Evals & Red Teaming"]
        LS["LangSmith Tracing & Cost Recorder"]
        DE["DeepEval + Custom GEval Suite\n(evals/ + goldens/)"]
        PYRIT["PyRIT Red-Team Harness\n(redteam/ EN + JP)"]
    end

    Client -->|SSE / REST| AUTH
    AUTH --> RL --> G_IN --> ASK
    RETRIEVE --> G_RET
    HYP <-->|MultiServerMCPClient| G_TOOL
    G_TOOL --> MCP_RET & MCP_SQL & MCP_DEPT & MCP_EXP & MCP_WEB & MCP_APP
    JUDGE --> G_OUT --> G_HITL --> HITL
    HITL --> AP
    OUTCOME --> OUT_UI
    OUTCOME -->|Writeback Approved Knowledge| PG & PC

    HYP & JUDGE --> CACHE --> GW --> MAIN_M
    MCP_RET --> PG & PC
    MCP_SQL --> PG
    CoreLoop --> RD & MEM0
    CoreLoop --> LS
    DE --> EVAL_M
    PYRIT --> Edge
```

## 3. Multi-Tenant Isolation Model (Principle 8)

Every boundary enforces `tenant_id`:
- **Database (`PostgreSQL`)**: All 12 core tables and operational demo tables carry a non-nullable, indexed `tenant_id` column. Queries use `select_for_tenant(Model, tenant_id)` and `assert_same_tenant(...)`.
- **Cache (`Redis`)**: Keys are namespaced as `alba:llm_cache:{tenant_id}:{model}:{prompt_version}:{input_hash}:{retrieval_hash}`.
- **Rate Limiting (`Redis`)**: Buckets are isolated under `alba:rl:{scope}:{tenant_id}[:{subject_id}]`.
- **LLM Gateway (`Portkey / Bifrost / TensorZero / Mesh`)**: Every call injects `tenant_id`, `task`, and `prompt_version` into gateway metadata headers (`x-portkey-metadata` and `x-alba-tenant-id`).
