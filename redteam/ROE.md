# ALBA ONE — Red-Team Rules of Engagement (`redteam/ROE.md`)

**Company:** ALBACONNECT Inc. (Tokyo; ISMS-certified — ISO/IEC 27001)  
**Protected by `.github/CODEOWNERS`:** Changes to this file, `redteam/allowed_targets.yaml`, `redteam/quarantine.yaml`, and `.github/workflows/redteam-*.yml` require explicit approval from `@albaconnect/security-owners`.

---

## 1. Four Independent Target-Isolation Controls

1. **Control 1 — Code-Level Allowlist (`redteam/allowed_targets.yaml`)**:
   - Explicitly enumerates every permitted target with `environment: staging | production | local` and `allow_production: false` by default.
   - Any host or target identifier not present in `allowed_targets` is rejected immediately (`PermissionError`).
2. **Control 2 — Target Identity & Self-Reported Environment Handshake**:
   - Before sending a single adversarial prompt, the runner calls the target's health/build-info endpoint (`/api/v1/health/deep` or `get_target_identity()`) and inspects its self-reported `app_env`, `app_version`, and allowed synthetic `tenant_ids`.
   - If the target reports `app_env == "production"` while the run was configured for `staging` or `local` (e.g., due to DNS misconfiguration, hostname alias, or wrong secret), the runner **aborts immediately before any attack payload is sent**.
3. **Control 3 — Repository & Branch Protection (`.github/CODEOWNERS`)**:
   - Scheduled workflows (`redteam-scheduled.yml`) execute **only** from the default branch (`refs/heads/main`) on CI runners outside the production cluster—never from forks or PR branches, and never as a CronJob inside the production cluster.
   - Required GitHub branch-protection settings are documented in `docs/SECURITY.md` (`TODO(owner)` to enable in GitHub settings).
4. **Control 4 — Credential & Tenant Segregation**:
   - Red-team runs authenticate exclusively as dedicated synthetic tenants (`tenant_fictional_alpha`, `tenant_fictional_other`, `tenant_fictional_canary`).
   - Scheduled CI jobs only have access to the `staging` GitHub Environment. Production probe credentials live exclusively in the `production-probe` GitHub Environment behind required human reviewers, are strictly read-only, and belong to `tenant_fictional_canary`.

---

## 2. Production Break-Glass Policy & Forbidden Production Scopes

- **Default Rule**: Scheduled red-team campaigns (`redteam-smoke`, `redteam-nightly`, `redteam-weekly`) target **staging only**.
- **Break-Glass Conditions**: Running against a `production` target requires **all** of the following simultaneously:
  1. Manual `workflow_dispatch` on `.github/workflows/redteam-breakglass-prod.yml` with `justification`, `ticket_id`, `time_window_minutes`, and `scope` (`guardrail_heartbeat | benign_smoke | canary_injection_readonly`).
  2. Approval by a required reviewer in the `production-probe` GitHub Environment (`approved_by` recorded in `redteam_runs` and the security audit stream).
  3. Environment variable `REDTEAM_PROD_ENABLED=1` AND CLI flag `--production-authorised`.
  4. Execution timestamp strictly inside `[authorized_at, authorized_at + time_window_minutes]`.
- **Mandatory `production_safe: true` Filter**:
  - In production break-glass mode, the runner filters the scenario catalog to `scenario.production_safe is True` only (guardrail heartbeat probes, benign requests, and harmless read-only canary-injection prompts against the synthetic canary tenant).
  - **Strictly Forbidden in Production (`production_safe: false`)**:
    - Infrastructure or Kubernetes probing
    - Load, token-budget, or cost/loop abuse (`cost_and_loop_abuse`)
    - SSRF and DNS rebinding (`ssrf_and_dns_rebinding`)
    - SQL injection or database probing (`sql_readonly_injection`)
    - Any scenario that writes or mutates state (`hitl_and_write_tool_bypass`, `cache_poisoning_cross_tenant`)
    - Any scenario touching a real customer tenant (`cross_tenant_isolation` across non-canary tenants)

---

## 3. Automatic Abort & Safety Circuit Breakers

Every run enforces:
- **Global Run Timeout**: `max_run_duration_seconds` (default `900s`).
- **Per-Run Budget Cap**: `max_cost_usd_per_run` (default `$1.00`) and `max_tokens_per_run` (`250,000`).
- **Rate Limit**: `max_requests_per_minute` (default `120 RPM` in staging, `20 RPM` in production break-glass).
- **Target Health Circuit Breaker**: Automatic abort if the target's 5xx/transport error rate exceeds `max_target_error_rate` (default `0.10`) or p95 latency exceeds `max_target_latency_ms` (default `15000ms`).
