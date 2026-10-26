# ALBA ONE — Guardrail Coverage Matrix (`docs/GUARDRAIL_COVERAGE.md`)

- **Verification Date:** 2026-10-24
- **Primary Sources Verified:**
  1. [Languages supported by Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html)
  2. [Distribute guardrail inference across AWS Regions](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region.html) & [Supported Regions for cross-Region guardrail inference](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region-support.html)
  3. [Boto3 Bedrock `create_guardrail` API Reference](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock/client/create_guardrail.html)

## 1. Verified AWS Bedrock Guardrails Findings (2026-10-24)

1. **Classic Tier vs. Standard Tier (`tierConfig={'tierName': 'STANDARD'}`)**:
   - **Classic tier** (`CLASSIC`) only supports **English, French, and Spanish** for Content Filters, Prompt Attacks, Denied Topics, and Contextual Grounding. Japanese is **unsupported** on Classic tier.
   - **Standard tier** (`STANDARD`) supports **Japanese (`Optimized and supported`)** and **English (`Optimized and supported`)** for Content Filters, Prompt Attacks, Denied Topics, and Contextual Grounding.
   - `infra/bedrock/create_guardrail.py` enforces `BEDROCK_GUARDRAIL_TIER=STANDARD` (from config) and raises a `ValueError` if `CLASSIC` tier is configured while Japanese protection is required.
2. **Cross-Region Inference Requirement (`crossRegionConfig`)**:
   - Standard tier requires a system-defined cross-Region guardrail profile (`crossRegionConfig={'guardrailProfileIdentifier': settings.bedrock_guardrail_cross_region_profile}`).
   - For source region `ap-northeast-1` (Tokyo), the official AWS profile identifier is **`apac.guardrail.v1:0`**, which can route guardrail evaluation across **`ap-northeast-1` (Tokyo), `ap-northeast-3` (Osaka), `ap-northeast-2` (Seoul), `ap-south-1` (Mumbai), `ap-southeast-1` (Singapore), and `ap-southeast-2` (Sydney)**.
   - Consequently, Bedrock Standard-tier guardrail evaluation is **not** a Japan-only processing path (documented in `docs/SECURITY.md` and `docs/DATA_FLOWS.md`).
3. **Word Filters (`wordPolicyConfig`)**:
   - As of 2026-10-24, AWS Bedrock Word Filters only list **English, French, and Spanish (`Supported`)**. **Japanese is NOT supported** by Bedrock Word Filters even when the guardrail uses Standard tier.
   - All Japanese word filtering, competitor-mention blocking, and forbidden business phrases are therefore enforced by our **local deterministic validator + Guardrails AI validator** running in parallel.
4. **Sensitive Information / PII (`sensitiveInformationPolicyConfig`)**:
   - Predefined Bedrock PII entity types (`NAME`, `EMAIL`, `PHONE`, `US_SOCIAL_SECURITY_NUMBER`) are not tailored to Japanese formats (12-digit My Number / マイナンバー, Japanese postal codes `〒NNN-NNNN`, domestic phone numbers `03-...` / `090-...`, or kanji/kana full names).
   - We configure custom regex entries (`regexesConfig`) in Bedrock for My Number, Japanese phones, and postal codes **and** always execute our local `PIIRedactor` (`kb/pii.py`) in parallel on every request.
5. **Contextual Grounding (`contextualGroundingPolicyConfig`)**:
   - Standard tier lists Japanese as `Optimized and supported`, while Classic tier only supports English/French/Spanish. In addition to Bedrock's `GROUNDING` and `RELEVANCE` checks, ALBA ONE enforces a local deterministic citation-existence check (`output_layer.py`) and a gateway-routed `JUDGE_MODEL` claim-to-citation entailment validator (`guardrails_ai.py`) so Japanese outputs never rely solely on probabilistic cloud grounding.

## 2. Policy × Language × Engine Coverage Matrix

At runtime, `guardrails/bedrock.py` executes `bedrock-runtime.apply_guardrail` **in parallel** (`asyncio.gather`) with our deterministic local validators and combines decisions using **most restrictive wins** (`block > mask > escalate > pass`). Guardrails AI validators are invoked selectively only where noted below.

| Policy / Check | Layer(s) | Lang | Bedrock Engine Status (Standard Tier) | Local Deterministic Engine | Guardrails AI Engine | Effective Runtime Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **System Prompt Integrity & Secret Lint** | `1. prompt` | `ja`, `en` | Not applicable (static prompt files) | **Supported** (secret regexes + instruction hierarchy check) | Not needed | Local deterministic linter on `prompts/<name>/<version>.md` |
| **Harmful Content (Hate, Violence, Sexual, Insults, Misconduct)** | `2. input`, `3. output` | `ja`, `en` | **Supported (`Optimized` on `STANDARD`; `ja` unsupported on `CLASSIC`)** | **Supported** (keyword blocklist backup) | Not needed | Parallel Bedrock `ApplyGuardrail` + local backup (`most_restrictive_wins`) |
| **Prompt Attack / Injection Override** | `2. input`, `4. retriever`, `5. tool` | `ja`, `en` | **Supported (`Optimized` on `STANDARD`; `ja` unsupported on `CLASSIC`)** | **Supported** (JP/EN injection regex heuristics) | Not needed | Parallel Bedrock `PROMPT_ATTACK` + local JP/EN heuristics |
| **Denied Topics (Legal/Medical/Out-of-Scope Advice)** | `2. input`, `3. output` | `ja`, `en` | **Supported (`Optimized` on `STANDARD`; `ja` unsupported on `CLASSIC`)** | **Supported** (JP/EN topic scope patterns) | **Needs Guardrails AI** (for nuanced out-of-scope topic classification) | Parallel Bedrock `topicPolicyConfig` + local scope rules + selective Guardrails AI |
| **Word Filters & Competitor Mentions** | `2. input`, `3. output` | `en` | **Supported** (`wordPolicyConfig`) | **Supported** (exact/case-folded match) | **Needs Guardrails AI** (`CompetitorCheck`) | Parallel Bedrock + local + Guardrails AI competitor validator |
| **Word Filters & Competitor Mentions** | `2. input`, `3. output` | `ja` | **Unsupported in Bedrock** (EN/FR/ES only in AWS docs) | **Supported** (NFKC-normalized JP word/competitor matcher) | **Needs Guardrails AI** (JP competitor/business-rule validator) | **Local deterministic JP matcher + Guardrails AI** (never relies on Bedrock for JP words) |
| **Western PII (Email, Credit Card, IPv4)** | `2. input`, `3. output`, `4. retriever` | `ja`, `en` | **Supported** (`piiEntitiesConfig`) | **Supported** (`PIIRedactor`) | Not needed | Parallel Bedrock `ANONYMIZE` + local `PIIRedactor` (`mask`) |
| **Japanese PII (My Number, JP Phone, `〒` Postal, JP Names)** | `2. input`, `3. output`, `4. retriever` | `ja` | **Partial** (via custom `regexesConfig` only; predefined PII lacks JP My Number/postal) | **Supported** (`PIIRedactor` with NFKC + configurable JP names) | Not needed | Parallel Bedrock `regexesConfig` + mandatory local `PIIRedactor` (`mask`) |
| **Contextual Grounding & Citation Schema** | `3. output` | `en` | **Supported** (`STANDARD` & `CLASSIC` `GROUNDING`/`RELEVANCE`) | **Supported** (Pydantic v2 citation-existence check) | **Needs Guardrails AI** (`JUDGE_MODEL` entailment validator) | Parallel Bedrock grounding + local citation ID check + `JUDGE_MODEL` entailment |
| **Contextual Grounding & Citation Schema** | `3. output` | `ja` | **Supported on `STANDARD` only** (`Unsupported` on `CLASSIC`) | **Supported** (Pydantic v2 citation-existence check) | **Needs Guardrails AI** (`JUDGE_MODEL` JP claim-to-citation entailment) | Parallel Bedrock (`STANDARD`) + mandatory local citation check + `JUDGE_MODEL` JP entailment |
| **Tool Allowlist, Read-Only SQL & SSRF Guard** | `5. tool` | `ja`, `en` | Not supported natively by Bedrock | **Supported** (allowlist, SQL AST/regex guard, SSRF IP/domain guard) | **Needs Guardrails AI** (JSON-schema argument validator) | Local deterministic SQL/SSRF/allowlist guard + schema check |
| **HITL Role, Risk & Confidence Gate** | `6. hitl` | `ja`, `en` | Not supported natively by Bedrock | **Supported** (policy table: `write` tools, risk/confidence thresholds, approver RBAC) | Not needed | Local deterministic HITL policy gate (`escalate` / `block`) |
| **Operational Budgets, Step Caps & Kill Switch** | `7. ops` | `ja`, `en` | Not supported natively by Bedrock | **Supported** (token/USD budget, max steps, max tool calls, circuit breaker, kill switch) | Not needed | Local deterministic operational controller (`block`) |
