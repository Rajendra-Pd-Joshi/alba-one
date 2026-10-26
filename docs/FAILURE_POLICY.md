# ALBA ONE — Guardrail & Dependency Failure Policy (`docs/FAILURE_POLICY.md`)

When an external guardrail or infrastructure dependency is unreachable, times out, or returns an unexpected 5xx error, ALBA ONE enforces an explicit per-layer **Fail-Closed vs. Fail-Open** policy.

## 1. Per-Layer Failure Policy Table

| Layer / Component | Failure Mode | Policy | Runtime Behaviour when Dependency Fails |
| :--- | :--- | :--- | :--- |
| **1. Prompt Guardrail (`prompt_layer.py`)** | Missing prompt file or leaked secret in template | **FAIL-CLOSED (`block`)** | Refuses to construct the LLM call; logs a `GuardrailEvent(layer="prompt", action="block")`. |
| **2. Input Guardrail (`input_layer.py`)** | AWS Bedrock `ApplyGuardrail` unreachable / timeout / 5xx | **FAIL-CLOSED (`block`)** | Local deterministic validators still execute; even if local checks pass, the layer returns `action="block"` with a polite bilingual "temporarily unavailable" refusal (`GUARDRAIL_UNAVAILABLE`) and logs an operational `GuardrailEvent`. |
| **3. Output Guardrail (`output_layer.py`)** | AWS Bedrock `ApplyGuardrail` or Grounding check unreachable | **FAIL-CLOSED (`block`)** | Never streams or returns an unverified LLM response to the user; returns a polite bilingual refusal and logs a `GuardrailEvent(layer="output", action="block", policy="bedrock_unavailable_fail_closed")`. |
| **4. Retriever Guardrail (`retriever_layer.py`)** | Bedrock chunk scan unreachable or chunk fails ACL/injection check | **FAIL-CLOSED per chunk (`block`)** | Drops any chunk that cannot be verified or fails local ACL/PII/injection checks; if zero chunks remain, pipeline returns `"insufficient_evidence"`. |
| **5. Tool Guardrail (`tool_layer.py`)** | Unknown MCP server/tool, schema mismatch, SQL/SSRF violation, or rate-limit failure | **FAIL-CLOSED (`block`)** | Blocks the tool invocation before execution; `write`-class tools without a verified `ApprovalRecord` are unconditionally blocked. |
| **6. HITL Guardrail (`hitl_layer.py`)** | Missing approver role, expired approval window, or unapproved side-effect | **FAIL-CLOSED (`escalate` / `block`)** | Halts graph execution via LangGraph `interrupt()` or blocks execution until an authorized `approver`/`admin` records approval. |
| **7. Operational Guardrail (`ops_layer.py`)** | Kill switch active, token/cost budget exceeded, or max steps/tool calls exceeded | **FAIL-CLOSED (`block`)** | Immediately aborts the run and returns a bilingual budget/kill-switch message. |
| **Observability / LangSmith (`observability/`)** | LangSmith API unreachable or timeout | **FAIL-OPEN (`pass` with warning log)** | Local `llm_calls` and `guardrail_events` rows are still recorded in PostgreSQL; user requests are not blocked by external tracing outages. |
