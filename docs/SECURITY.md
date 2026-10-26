# ALBA ONE — Security, Authentication, Encryption & Data Residency (`docs/SECURITY.md`)

**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified — ISO/IEC 27001)

## 1. Prominent Notice: AWS Bedrock Guardrails Standard Tier & Cross-Region APAC Routing

To support Japanese (`ja`) in Amazon Bedrock Guardrails for Content Filters, Prompt Attacks, Denied Topics, and Contextual Grounding, AWS requires the **Standard tier** (`BEDROCK_GUARDRAIL_TIER=STANDARD`) paired with a cross-Region inference profile (`BEDROCK_GUARDRAIL_CROSS_REGION_PROFILE=apac.guardrail.v1:0`).

> **IMPORTANT DATA RESIDENCY NOTICE (Cross-Region APAC Inference):**
> When calling `bedrock-runtime:ApplyGuardrail` with `apac.guardrail.v1:0` from `ap-northeast-1` (Tokyo), AWS may route guardrail evaluation payloads across any Region in the APAC geographic profile:
> - `ap-northeast-1` (Tokyo), `ap-northeast-3` (Osaka), `ap-northeast-2` (Seoul), `ap-south-1` (Mumbai), `ap-southeast-1` (Singapore), `ap-southeast-2` (Sydney).
>
> **This is NOT a Japan-only processing path.** While the guardrail resource configuration stays in `ap-northeast-1`, input prompts, retrieved chunks, and output candidates checked by Bedrock Guardrails may traverse other APAC AWS Regions over Amazon's encrypted network.

---

## 2. Enterprise OIDC / JWKS Authentication & Confidential Browser Flow (Phase 10)

### 2.1 API JWT Verification (`core/auth_oidc.py` & `core/tenancy_logic.py`)
- **Maintained Cryptography**: Uses `cryptography` (and `PyJWT[crypto]`) to verify asymmetric signatures against the enterprise IdP's JWKS endpoint.
- **Strict Algorithm Allowlist**: Defaults to `OIDC_ALLOWED_ALGORITHMS=RS256,ES256`. Rejects `alg: "none"` and all symmetric HMAC (`HS256`/`HS384`/`HS512`) tokens unconditionally regardless of the token header.
- **Standard Claim Verification**: Selects public key by `kid`; verifies `iss` (exact match with `OIDC_ISSUER`), `aud` (must contain `OIDC_AUDIENCE`), `exp`, `nbf`, `iat` (`OIDC_MAX_TOKEN_AGE_SECONDS`, default 3600s; `OIDC_LEEWAY_SECONDS`, default 30s), and requires `sub`. Rejects ID tokens (`typ: "id_token"` or `token_use: "id"`) so only access tokens are accepted.
- **Verified Claim Mapping**: `tenant_id` (`OIDC_CLAIM_TENANT`), `roles` (`OIDC_CLAIM_ROLES`), and `lang` (`OIDC_CLAIM_LANG`) are extracted **strictly from the verified JWT**, never from headers, query parameters, or request bodies. Unknown roles are dropped; a missing tenant claim returns HTTP `403`; any request supplying a conflicting `X-Tenant-Id` header or `tenant_id` query parameter is rejected with HTTP `403` and logged as a security event (`security_event_conflicting_tenant_id`).
- **Step-Up MFA Verification**: Approver and Knowledge Steward actions optionally require an authentication-strength claim (`OIDC_STEP_UP_CLAIM=amr` or `acr`, matching `OIDC_STEP_UP_VALUES`, `TODO(owner)` per IdP) when `OIDC_REQUIRE_STEP_UP_FOR_APPROVALS=true`.
- **Anti-Amplification JWKS Cache**: Fetches JWKS strictly over HTTPS (HTTP permitted only when `APP_ENV=development`) with connect/read timeouts (`3.0s`), byte size cap (`64 KiB`), and TTL cache (`JWKS_TTL_SECONDS=300`). On an unknown `kid`, refreshes at most once per `JWKS_MIN_REFRESH_INTERVAL_SECONDS` (`30s`) to prevent random-`kid` DoS floods. If refresh fails, serves cached keys up to `JWKS_MAX_STALE_SECONDS` (`3600s`) and increments an alert counter (`AlbaOneJWKSRefreshFailingStaleCache`), then fails closed with HTTP `503`. Never logs raw tokens (logs `kid`, `iss`, and `error_type` only).

### 2.2 Browser Confidential Client Flow (`apps/web/src/lib/auth/oidc-session.ts`)
- The Next.js server acts as the confidential OIDC client using **Authorization Code + PKCE (`S256`)**.
- Tokens are stored only inside an `httpOnly`, `Secure`, `SameSite=Lax` session cookie (`alba_session`) and forwarded by the server-side proxy (`apps/web/src/app/api/proxy/[...path]/route.ts`) as an `Authorization: Bearer ...` header to FastAPI.
- Access tokens never reach browser JavaScript and are never placed in `NEXT_PUBLIC_*` variables.
- **Vendor-Neutral IdP Configuration Requirements (`TODO(owner)`)**:
  - **Grant Type**: Authorization Code with PKCE (`S256` required), Client Authentication (`client_secret_basic` or `private_key_jwt`).
  - **Redirect URI**: `https://<host>/api/auth/callback`
  - **Post-Logout Redirect URI**: `https://<host>/ja` (and `/en`)
  - **Scopes**: `openid profile email` + custom API scope issuing access tokens for audience `OIDC_AUDIENCE`.
  - **Access Token Claims**: `sub`, `tenant_id` (or configured `OIDC_CLAIM_TENANT`), `roles` (`viewer`, `analyst`, `knowledge_steward`, `approver`, `admin`), `lang` (`ja` | `en`), `amr`/`acr` (for MFA verification).

### 2.3 Service-to-Service (`S2S`) Authentication & Dual-Secret Rotation
- Calls from the API to MCP servers carry a short-lived HMAC-signed internal token (`InternalBearerRotator` in `core/auth_oidc.py`) embedding `tenant_id`, `sub` (`user_id`), and `role` so each MCP server enforces ACLs independently, paired with Istio `STRICT` mTLS in Kubernetes (`deploy/security/mtls-and-pss.yaml`).
- During secret rotation, `InternalBearerRotator` accepts both `INTERNAL_S2S_CURRENT_SECRET` and `INTERNAL_S2S_PREVIOUS_SECRET` until `INTERNAL_S2S_PREVIOUS_SECRET_EXPIRES_AT` (see `deploy/runbooks/key-rotation.md`).

---

## 3. Startup Fail-Closed Enforcement (`core/startup_checks.py` & `apps/web/scripts/check-startup.mjs`)

- **Unset or Unknown `APP_ENV` Treated as Production-Strict**: Only `development`, `test`, `staging`, and `production` are valid. Any unset or unknown value defaults to `production` strictness and aborts startup.
- **All Violations Reported Together**: In `staging` and `production`, startup aborts with a single aggregated error listing every failing rule if any check fails (see `core/startup_checks.py`).

---

## 4. On-Premise Knowledge Database Connection Requirements

The customer's on-premise PostgreSQL database is **never** deployed or managed by our cloud Terraform manifests. Connections from `kb/extractors.py` and `mcp-sql-readonly` must satisfy:
1. **Transport Encryption**: Mutual TLS (`sslmode=verify-full` with client certificate `onprem-kb-client-mtls-cert`) over AWS Direct Connect or Site-to-Site VPN.
2. **Least-Privilege Read-Only Role**: Dedicated PostgreSQL role (`alba_kb_readonly`) with `SET default_transaction_read_only = on`, `statement_timeout = '5s'`, and `SELECT` granted **only** on DBA-approved views (`v_kb_*` in `infra/seed/02_kb_readonly_views.sql`).

---

## 5. Outbound External Search & Page Fetch Controls (Phase 5)

1. **Outbound Query Guardrail (`guardrails/outbound_query.py`)**: Scrubs PII, blocks secrets, and enforces `OUTBOUND_QUERY_POLICY=block` in production against tenant `sensitive_terms`.
2. **SSRF & Domain Policy (`fetch_page`)**: Blocks private, loopback, link-local, and cloud-metadata IP ranges (`169.254.169.254`), re-verifies every redirect, and routes external MCP egress exclusively through the domain-allowlisted egress proxy (`deploy/helm/alba-one/templates/networkpolicies.yaml`).
3. **External Provider Legal & Data-Retention Review (`TODO(owner)`)**:
   - **Tavily (`api.tavily.com`) Data Retention & Training Terms:** `TODO(owner)`
   - **Brave Search (`api.search.brave.com`) Data Retention & Training Terms:** `TODO(owner)`
   - **Firecrawl (`api.firecrawl.dev`) Data Retention & Training Terms:** `TODO(owner)`

---

## 6. Post-Deployment Red Teaming, Branch Protection & GitHub Environments (Phase 11)

Per `redteam/ROE.md` and `.github/CODEOWNERS`, the repository owner must configure the following settings in GitHub before enabling scheduled or break-glass red-team workflows (`TODO(owner)` — documented here, not claimed as pre-applied):
1. **Branch Protection on `main`**:
   - Require pull request reviews before merging (`Required approving reviews >= 1`).
   - Enable **Require review from Code Owners** (enforces `@albaconnect/security-owners` sign-off on `redteam/ROE.md`, `redteam/allowed_targets.yaml`, `redteam/quarantine.yaml`, `redteam/corpus/`, and `.github/workflows/redteam-*.yml`).
   - Require status checks to pass before merging (`Secret Scan (gitleaks)`, `Lint, Type-Check, Unit & Contract Tests (Python 3.12)`, `Container Hardening & Trivy Scan`).
   - Do not allow bypassing the above settings.
2. **GitHub Environments**:
   - `staging`: Contains synthetic staging tenant credentials (`tenant_fictional_alpha`, `tenant_fictional_other`). Restricted to `main` branch.
   - `production-probe`: Contains read-only synthetic canary tenant credentials (`tenant_fictional_canary`) ONLY. Configure **Required reviewers** (`@albaconnect/security-owners`) and restrict deployment branches to `main`.
3. **Regression & Containment Policy**:
   - Automated runs **never** trigger `OPS_KILL_SWITCH=true`.
   - Critical bypasses block promotion, fail Argo Rollouts canary analysis (`redteam_critical_bypass_count`), page a human, and recommend blast-radius-ranked containment options (`redteam/incidents.py`).
   - Optional `REDTEAM_AUTO_CONTAINMENT=degraded_mode` remains disabled until `degraded_mode_approved_by` in `redteam/allowed_targets.yaml` is signed off by `TODO(owner)`.
