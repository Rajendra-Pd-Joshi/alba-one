# ADR 0001: LLM Gateway Selection (Portkey vs. Bifrost vs. TensorZero vs. Mesh API)

- **Status:** Accepted (Phase 1 — Foundation)
- **Date:** 2026-10-24
- **Owners:** ALBACONNECT Engineering

## Context
ALBA ONE requires a unified, OpenAI-compatible LLM gateway (`base_url` abstraction) so that `apps/api/src/alba_one/gateway/llm.py` uses a single `ChatOpenAI` client while supporting:
1. Per-call tenant, task, and prompt-version attribution (`tenant_id`, `task`, `prompt_version`).
2. Declarative retries, request timeouts, and automatic model fallback chains (`MAIN_MODEL` -> `FALLBACK_MODELS`).
3. Zero-code provider swapping by changing environment variables (`GATEWAY_PROVIDER`, `GATEWAY_BASE_URL`, `GATEWAY_API_KEY`, `GATEWAY_EXTRA_HEADERS_JSON`).
4. ISMS-compliant auditability and cost tracking per tenant.

## Options Evaluated

| Criterion | **Portkey (Selected Default)** | **Bifrost (Maxim AI)** | **TensorZero** | **Mesh API** |
| :--- | :--- | :--- | :--- | :--- |
| **OpenAI SDK Compatibility** | Native `/v1/chat/completions` proxy & open-source gateway | High-throughput Go-based OpenAI proxy | Rust-based `/openai/v1` endpoint | Hosted OpenAI-compatible proxy |
| **Per-Call Metadata Headers** | `x-portkey-metadata` (JSON key-values indexed per request) | `x-bf-metadata` | `x-tensorzero-tags` | `x-mesh-metadata` |
| **Declarative Fallbacks & Retries** | Inline `x-portkey-config` JSON header or Virtual Keys | Server-side YAML config | `tensorzero.toml` function/variant routing | Dashboard routing policy |
| **Guardrail & Cost Hooks** | Native Bedrock / Guardrails AI hooks + token accounting | Lightweight proxy; external observability | Strong feedback & eval loop storage | Enterprise routing & spend caps |
| **Self-Hosted / Tokyo Region** | OSS gateway container or VPC deployment in `ap-northeast-1` | Single Go binary / Docker container | Rust binary + ClickHouse | Managed cloud / enterprise VPC |

## Decision
We select **Portkey** (`GATEWAY_PROVIDER=portkey`) as the default gateway because:
1. It accepts inline routing/fallback configs directly via the `x-portkey-config` HTTP header in addition to client-side LangChain `.with_fallbacks(...)`, allowing ALBA ONE to version fallback chains in `config/models.yaml` and `.env`.
2. Its `x-portkey-metadata` header cleanly indexes `tenant_id`, `task`, and `prompt_version` for per-tenant cost auditing.
3. Its open-source gateway runs statelessly inside Docker or AWS ECS in Tokyo (`ap-northeast-1`) for ISMS compliance.

## Environment Variable Configuration to Switch Gateways

No Python code changes are needed to switch gateways. Set the following in `.env`:

### 1. Portkey (Default)
```dotenv
GATEWAY_PROVIDER=portkey
GATEWAY_BASE_URL=https://api.portkey.ai/v1
GATEWAY_API_KEY=pk-live-...
GATEWAY_EXTRA_HEADERS_JSON={"x-portkey-provider":"openai"}
```

### 2. Bifrost
```dotenv
GATEWAY_PROVIDER=bifrost
GATEWAY_BASE_URL=http://bifrost:8080/v1
GATEWAY_API_KEY=bf-key-...
GATEWAY_EXTRA_HEADERS_JSON={"x-bf-provider":"openai"}
```

### 3. TensorZero
```dotenv
GATEWAY_PROVIDER=tensorzero
GATEWAY_BASE_URL=http://tensorzero-gateway:3000/openai/v1
GATEWAY_API_KEY=tz-key-...
GATEWAY_EXTRA_HEADERS_JSON={}
```

### 4. Mesh API
```dotenv
GATEWAY_PROVIDER=mesh
GATEWAY_BASE_URL=https://api.mesh.ai/v1
GATEWAY_API_KEY=mesh-key-...
GATEWAY_EXTRA_HEADERS_JSON={"x-mesh-org":"albaconnect"}
```
