"""Startup fail-closed security validator (`core/startup_checks.py` — Phase 10).

Executed before the application accepts traffic.
- Treats an unset or unknown `APP_ENV` as production-strict (`production`).
- Allows only `development`, `test`, `staging`, `production`.
- Refuses to boot when `APP_ENV` is `staging` or `production` (or unset/unknown) and ANY
  security violation is detected, reporting EVERY violation in a single error message.
- Collects non-fatal admin warnings (exposed on `/health/deep`) for report-only goldens,
  unset `TODO(owner)` thresholds, or unpriced models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

VALID_APP_ENVS: frozenset[str] = frozenset({"development", "test", "staging", "production"})
PROD_LIKE_ENVS: frozenset[str] = frozenset({"staging", "production"})

KNOWN_PLACEHOLDER_SECRETS: frozenset[str] = frozenset(
    {
        "",
        "changeme",
        "secret",
        "password",
        "alba_dev_password",
        "replace-with-portkey-api-key",
        "replace-with-openai-api-key",
        "replace-with-pinecone-api-key",
        "replace-with-cohere-api-key",
        "replace-with-bedrock-guardrail-id",
        "replace-with-langsmith-api-key",
        "replace-with-internal-s2s-secret",
        "test-gateway-key",
        "test-openai-key",
        "test-pinecone-key",
        "test-cohere-key",
    }
)


class StartupSecurityCheckError(RuntimeError):
    """Raised when one or more fail-closed startup checks fail."""

    def __init__(self, effective_env: str, violations: list[str]) -> None:
        self.effective_env = effective_env
        self.violations = list(violations)
        bullets = "\n".join(f"  - [{i + 1}] {v}" for i, v in enumerate(self.violations))
        super().__init__(
            f"ALBA ONE Startup Fail-Closed Check Failed (effective APP_ENV='{effective_env}', "
            f"{len(self.violations)} violation(s)):\n{bullets}"
        )


@dataclass(frozen=True)
class StartupCheckReport:
    """Result of running startup checks, including admin warnings for `/health/deep`."""

    effective_env: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() in ("1", "true", "yes", "on")


def _check_postgres_tls(db_url: str) -> bool:
    if not db_url:
        return False
    parsed = urlparse(db_url)
    qs = parse_qs(parsed.query)
    sslmode = (qs.get("sslmode", [""])[0] or "").strip().lower()
    return sslmode in ("require", "verify-ca", "verify-full")


def _check_redis_tls_and_auth(redis_url: str) -> tuple[bool, bool]:
    if not redis_url:
        return False, False
    parsed = urlparse(redis_url)
    is_tls = parsed.scheme.lower() == "rediss"
    has_auth = bool(parsed.password and parsed.password not in KNOWN_PLACEHOLDER_SECRETS)
    return is_tls, has_auth


def evaluate_startup_environment(
    env: Mapping[str, str],
    *,
    unreviewed_goldens_count: int = 0,
    unset_thresholds_count: int = 0,
    unpriced_models: list[str] | None = None,
) -> StartupCheckReport:
    """Evaluate all startup security invariants against `env` without failing on the first rule."""
    raw_env = (env.get("APP_ENV") or "").strip().lower()
    violations: list[str] = []
    warnings: list[str] = []

    if not raw_env:
        effective_env = "production"
        violations.append(
            "APP_ENV is unset; treating environment as production-strict. "
            "Set APP_ENV explicitly to one of: development, test, staging, production."
        )
    elif raw_env not in VALID_APP_ENVS:
        effective_env = "production"
        violations.append(
            f"APP_ENV='{raw_env}' is invalid; treating as production-strict. "
            "Allowed values: development, test, staging, production."
        )
    else:
        effective_env = raw_env

    if effective_env in PROD_LIKE_ENVS:
        # 1. Auth stub & OIDC HTTPS checks
        if _is_truthy(env.get("AUTH_STUB_ENABLED", "false")):
            violations.append("AUTH_STUB_ENABLED=true is forbidden in staging/production.")
        if _is_truthy(env.get("ACCEPT_DEV_AUTH_HEADERS", "false")):
            violations.append("ACCEPT_DEV_AUTH_HEADERS=true is forbidden in staging/production.")

        oidc_issuer = (env.get("OIDC_ISSUER") or "").strip()
        oidc_audience = (env.get("OIDC_AUDIENCE") or "").strip()
        oidc_jwks_url = (env.get("OIDC_JWKS_URL") or "").strip()
        if not oidc_issuer or not oidc_issuer.lower().startswith("https://"):
            violations.append("OIDC_ISSUER must be set and use https:// in staging/production.")
        if not oidc_audience:
            violations.append("OIDC_AUDIENCE must be set in staging/production.")
        if not oidc_jwks_url or not oidc_jwks_url.lower().startswith("https://"):
            violations.append("OIDC_JWKS_URL must be set and use https:// in staging/production.")

        # 2. Debug / reload / OpenAPI docs flags
        for flag in ("DEBUG", "RELOAD", "UVICORN_RELOAD", "OPENAPI_DOCS_ENABLED"):
            if _is_truthy(env.get(flag)):
                violations.append(f"{flag}=true is forbidden in staging/production.")

        # 3. CORS wildcard checks
        cors_origins = [
            o.strip() for o in (env.get("CORS_ALLOWED_ORIGINS") or "").split(",") if o.strip()
        ]
        allow_creds = _is_truthy(env.get("CORS_ALLOW_CREDENTIALS", "true"))
        if "*" in cors_origins:
            violations.append("CORS_ALLOWED_ORIGINS cannot contain wildcard '*' in staging/production.")
        if allow_creds and ("*" in cors_origins or not cors_origins):
            violations.append(
                "CORS_ALLOW_CREDENTIALS=true requires explicit non-wildcard CORS_ALLOWED_ORIGINS."
            )

        # 4. Known placeholder or development secrets
        for sec_var in (
            "GATEWAY_API_KEY",
            "OPENAI_API_KEY",
            "PINECONE_API_KEY",
            "COHERE_API_KEY",
            "INTERNAL_S2S_CURRENT_SECRET",
        ):
            val = (env.get(sec_var) or "").strip()
            if val in KNOWN_PLACEHOLDER_SECRETS:
                violations.append(f"{sec_var} is unset or matches a known placeholder/dev value.")

        # 5. Database TLS & dev password check
        db_url = (env.get("DATABASE_URL") or "").strip()
        if not _check_postgres_tls(db_url):
            violations.append(
                "DATABASE_URL must enforce TLS (`sslmode=require` or `sslmode=verify-full`) in staging/production."
            )
        if "alba_dev_password" in db_url:
            violations.append("DATABASE_URL contains development password 'alba_dev_password'.")

        # 6. Redis TLS & auth check
        redis_tls, redis_auth = _check_redis_tls_and_auth((env.get("REDIS_URL") or "").strip())
        if not redis_tls or not redis_auth:
            violations.append(
                "REDIS_URL must use TLS (`rediss://`) and a non-placeholder password in staging/production."
            )

        # 7. Trace content capture
        if _is_truthy(env.get("TRACE_CAPTURE_CONTENT", "false")):
            violations.append("TRACE_CAPTURE_CONTENT=true is forbidden in staging/production (PII/ISMS policy).")

        # 8. Guardrail & kill-switch configuration
        gr_id = (env.get("BEDROCK_GUARDRAIL_ID") or "").strip()
        gr_ver = (env.get("BEDROCK_GUARDRAIL_VERSION") or "").strip()
        if not gr_id or gr_id in KNOWN_PLACEHOLDER_SECRETS or not gr_ver:
            violations.append("BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION must be configured.")
        if (env.get("BEDROCK_GUARDRAIL_TIER") or "STANDARD").strip().upper() != "STANDARD":
            violations.append("BEDROCK_GUARDRAIL_TIER must be 'STANDARD' for Japanese support.")
        if "OPS_KILL_SWITCH" not in env:
            violations.append("OPS_KILL_SWITCH must be explicitly configured ('true' or 'false').")

        gr_mode = (env.get("GUARDRAIL_MODE") or "enforce").strip().lower()
        if gr_mode == "monitor":
            if _is_truthy(env.get("ALLOW_GUARDRAIL_MONITOR_IN_PROD", "false")):
                msg = (
                    "LOUD WARNING: GUARDRAIL_MODE=monitor is active in staging/production "
                    "via ALLOW_GUARDRAIL_MONITOR_IN_PROD=true."
                )
                logger.warning(msg)
                warnings.append(msg)
            else:
                violations.append(
                    "GUARDRAIL_MODE=monitor is forbidden in staging/production unless "
                    "ALLOW_GUARDRAIL_MONITOR_IN_PROD=true is explicitly set."
                )

        # 9. Outbound fetch & query policies
        fetch_pol = (env.get("FETCH_DOMAIN_POLICY") or "denylist").strip().lower()
        if fetch_pol == "open_public" and not _is_truthy(env.get("ALLOW_OPEN_PUBLIC_FETCH_IN_PROD")):
            violations.append(
                "FETCH_DOMAIN_POLICY=open_public is forbidden in staging/production without "
                "ALLOW_OPEN_PUBLIC_FETCH_IN_PROD=true."
            )
        outbound_pol = (env.get("OUTBOUND_QUERY_POLICY") or "block").strip().lower()
        if outbound_pol == "generalize" and not _is_truthy(env.get("ALLOW_OUTBOUND_GENERALIZE_IN_PROD")):
            violations.append(
                "OUTBOUND_QUERY_POLICY=generalize is forbidden in staging/production without "
                "ALLOW_OUTBOUND_GENERALIZE_IN_PROD=true (use 'block')."
            )

    # Non-fatal warnings surfaced on /health/deep for admins
    if unreviewed_goldens_count > 0:
        warnings.append(f"{unreviewed_goldens_count} golden dataset item(s) remain in 'draft' status.")
    if unset_thresholds_count > 0:
        warnings.append(f"{unset_thresholds_count} eval threshold(s) remain 'TODO(owner)' (report-only mode).")
    if unpriced_models:
        warnings.append(f"Unpriced configured model(s): {', '.join(sorted(set(unpriced_models)))}.")

    return StartupCheckReport(
        effective_env=effective_env,
        violations=violations,
        warnings=warnings,
    )


def enforce_startup_checks(
    env: Mapping[str, str],
    *,
    unreviewed_goldens_count: int = 0,
    unset_thresholds_count: int = 0,
    unpriced_models: list[str] | None = None,
) -> StartupCheckReport:
    """Run all startup checks and raise `StartupSecurityCheckError` listing every violation."""
    report = evaluate_startup_environment(
        env,
        unreviewed_goldens_count=unreviewed_goldens_count,
        unset_thresholds_count=unset_thresholds_count,
        unpriced_models=unpriced_models,
    )
    if report.violations:
        raise StartupSecurityCheckError(report.effective_env, report.violations)
    return report
