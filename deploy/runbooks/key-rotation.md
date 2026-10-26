# ALBA ONE — Secret Rotation & Emergency Leak Response Runbook (`deploy/runbooks/key-rotation.md`)

**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified — ISO/IEC 27001)

## 1. Secret Inventory Table

| Secret Name | Owner | Where Stored (Prod) | Consumer(s) | Rotation Interval | Rotation Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `INTERNAL_S2S_CURRENT_SECRET` / `INTERNAL_S2S_PREVIOUS_SECRET` | Platform Security (`TODO(owner)`) | AWS Secrets Manager (`alba-one/<env>/s2s`) -> K8s `ExternalSecret` | `api`, `worker`, all 22 `mcp-*` pods | `TODO(owner)` (e.g., 30 days) | Dual-secret window via `InternalBearerRotator` + Stakater Reloader rolling restart |
| `OIDC_JWKS` Signing Keys (`kid`) | Identity Team / IdP Admin (`TODO(owner)`) | Enterprise OIDC IdP (`/.well-known/jwks.json`) | `api` (`JWKSCache` in `core/auth_oidc.py`) | `TODO(owner)` (IdP managed, e.g., 90 days) | Automatic zero-downtime via `kid` lookup and rate-limited JWKS cache refresh |
| `DATABASE_URL` / RDS Credentials | DBA / Cloud Infra (`TODO(owner)`) | AWS IAM DB Auth (15m ephemeral tokens) or Secrets Manager (`alba-one/<env>/db`) | `api`, `worker`, `mcp-sql-readonly`, `mcp-approvals`, `mcp-decision-history` | Ephemeral (15m IAM token) or `TODO(owner)` (30 days) | Prefer short-lived IAM DB Auth tokens; fallback: Secrets Manager dual-user rotation + Reloader |
| `REDIS_URL` Auth Token | Cloud Infra (`TODO(owner)`) | AWS Secrets Manager (`alba-one/<env>/redis`) | `api`, `worker` | `TODO(owner)` (90 days) | ElastiCache `ROTATE` auth-token phase + ExternalSecret refresh + Reloader |
| `GATEWAY_API_KEY`, `OPENAI_API_KEY`, `PINECONE_API_KEY`, `COHERE_API_KEY`, `LANGSMITH_API_KEY` | AI Platform Owner (`TODO(owner)`) | AWS Secrets Manager (`alba-one/<env>/providers`) | `api`, `worker`, `mcp-knowledge-base` | `TODO(owner)` (90 days) | Create secondary key at provider -> update Secrets Manager -> ExternalSecret (5m) -> Reloader rolling restart -> revoke old key |
| On-Premise KB mTLS Client Cert (`onprem-kb-client-mtls-cert`) | Network & DBA Security (`TODO(owner)`) | cert-manager / AWS Private CA -> K8s TLS Secret | Istio egress / `mcp-knowledge-base` | `TODO(owner)` (30–90 days, auto-renew at 2/3 lifetime) | cert-manager automatic renewal prior to expiry |

---

## 2. Zero-Downtime Rotation Procedures

### 2.1 Internal Service-to-Service (`S2S`) Bearer Secret (`InternalBearerRotator`)
`alba_one.core.auth_oidc.InternalBearerRotator` accepts **two valid secrets simultaneously** (`INTERNAL_S2S_CURRENT_SECRET` and `INTERNAL_S2S_PREVIOUS_SECRET` until `INTERNAL_S2S_PREVIOUS_SECRET_EXPIRES_AT`):
1. **Step 1 (Promote current to previous & generate new current)**:
   - Generate a new 256-bit secret: `openssl rand -base64 32`.
   - In AWS Secrets Manager (`alba-one/production/s2s`), set:
     - `previous_secret` = old `current_secret`
     - `current_secret` = new 256-bit value
     - `previous_secret_expires_at` = current Unix timestamp + `3600` (1-hour overlap window)
2. **Step 2 (Automatic propagation & rolling restart)**:
   - `ExternalSecret` refreshes the Kubernetes Secret within 5 minutes (`refreshInterval: 5m`).
   - Stakater Reloader (`reloader.stakater.com/auto: "true"`) detects the Secret checksum change and triggers a rolling restart across `api`, `worker`, and `mcp-*` deployments (`PodDisruptionBudget` ensures zero downtime).
   - During the rolling restart, pods still on the old secret and pods on the new secret can verify each other's tokens seamlessly.
3. **Step 3 (Window expiry)**:
   - Once `previous_secret_expires_at` passes, `InternalBearerRotator` automatically stops accepting `previous_secret`. Clear `previous_secret` in Secrets Manager at convenience.

### 2.2 OIDC Signing Keys (`JWKS`)
- Handled automatically by `JWKSCache` (`core/auth_oidc.py`).
- When the IdP rotates keys and publishes a new `kid`, `JWKSCache.get_key(kid)` triggers at most one immediate refresh per `JWKS_MIN_REFRESH_INTERVAL_SECONDS` (default 30s, preventing random-`kid` amplification floods).
- If the IdP JWKS endpoint is temporarily unreachable during a scheduled refresh, `JWKSCache` continues serving cached public keys up to `JWKS_MAX_STALE_SECONDS` (default 3600s) while incrementing `stale_fallback_alert_count` (`AlbaOneJWKSRefreshFailingStaleCache`), then fails closed with HTTP `503`.

### 2.3 Database Credentials Trade-off (IAM DB Auth vs. Static Password Rotation)
- **Preferred (Production RDS)**: Enable `iam_database_authentication_enabled = true` (`deploy/terraform/main.tf`). The application exchanges its EKS Pod Identity / IRSA role for a 15-minute RDS auth token. Trade-off: RDS IAM auth has a connection-rate ceiling (~200 new connections/sec per instance), so connection pooling (`psycopg_pool` / RDS Proxy) is mandatory.
- **Fallback (Static Secret)**: Use AWS Secrets Manager two-user alternating rotation (`alba_app_a` / `alba_app_b`) paired with External Secrets + Stakater Reloader.

---

## 3. Emergency Revoke-and-Rotate Steps After a Suspected Leak

If `gitleaks` in CI, an audit log, or a security alert indicates a credential was exposed:
1. **Contain Immediately (< 5 minutes)**:
   - If an external provider key (`OPENAI_API_KEY`, `COHERE_API_KEY`, `PINECONE_API_KEY`, `GATEWAY_API_KEY`) leaked, revoke the key immediately in the provider console or activate `OPS_KILL_SWITCH=true` to halt outbound LLM/tool traffic.
   - If `INTERNAL_S2S_CURRENT_SECRET` leaked, overwrite **both** `current_secret` and `previous_secret` in AWS Secrets Manager with a fresh random value and set `previous_secret_expires_at=0`, then run:
     ```bash
     kubectl annotate externalsecret alba-one-external-secrets -n alba-one-prod force-sync="$(date +%s)" --overwrite
     ```
2. **Audit Blast Radius**:
   - Query `spans` and `audit_logs` in PostgreSQL for the affected time window (`SELECT * FROM spans WHERE created_at >= ...`) and inspect CloudTrail / IdP sign-in logs.
3. **Remediate Git History (if committed)**:
   - Purge the secret from Git refs, rotate all potentially co-exposed secrets, and record an ISMS incident post-mortem.
