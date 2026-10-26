"""FastAPI dependencies yielding `TenantContext` and `UserContext` via OIDC/JWKS (Phase 10)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from alba_one.core.auth_oidc import JWKSCache, OIDCConfig, OIDCVerifier
from alba_one.core.config import Settings, get_settings
from alba_one.core.error_catalog import AlbaError
from alba_one.core.logging import set_request_context
from alba_one.core.tenancy_logic import resolve_auth_claims
from alba_one.schemas.common import Language, TenantContext, UserContext, UserRole


@lru_cache(maxsize=4)
def _get_oidc_verifier(
    issuer: str,
    audience: str,
    jwks_url: str,
    allowed_algs: str,
    leeway: int,
    max_age: int,
    claim_tenant: str,
    claim_roles: str,
    claim_lang: str,
    step_up_claim: str,
    step_up_values: str,
    require_step_up: bool,
    app_env: str,
    jwks_ttl: int,
    jwks_stale: int,
    jwks_min_interval: int,
) -> OIDCVerifier | None:
    if not issuer or not audience or not jwks_url:
        return None
    algs = tuple(a.strip() for a in allowed_algs.split(",") if a.strip())
    step_vals = tuple(v.strip() for v in step_up_values.split(",") if v.strip())
    cfg = OIDCConfig(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        allowed_algorithms=algs,
        leeway_seconds=leeway,
        max_token_age_seconds=max_age,
        claim_tenant=claim_tenant,
        claim_roles=claim_roles,
        claim_lang=claim_lang,
        step_up_claim=step_up_claim,
        step_up_values=step_vals,
        require_step_up_for_approvals=require_step_up,
        app_env=app_env,
        jwks_ttl_seconds=jwks_ttl,
        jwks_max_stale_seconds=jwks_stale,
        jwks_min_refresh_interval_seconds=jwks_min_interval,
    )
    return OIDCVerifier(config=cfg, jwks_cache=JWKSCache(config=cfg))


async def get_current_contexts(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> tuple[TenantContext, UserContext]:
    """Extract `TenantContext` and `UserContext` from verified OIDC JWT (or dev stub when enabled)."""
    verifier = _get_oidc_verifier(
        settings.oidc_issuer,
        settings.oidc_audience,
        settings.oidc_jwks_url,
        settings.oidc_allowed_algorithms,
        settings.oidc_leeway_seconds,
        settings.oidc_max_token_age_seconds,
        settings.oidc_claim_tenant,
        settings.oidc_claim_roles,
        settings.oidc_claim_lang,
        settings.oidc_step_up_claim,
        settings.oidc_step_up_values,
        settings.oidc_require_step_up_for_approvals,
        settings.app_env,
        settings.jwks_ttl_seconds,
        settings.jwks_max_stale_seconds,
        settings.jwks_min_refresh_interval_seconds,
    )
    claims = resolve_auth_claims(
        dict(request.headers),
        stub_enabled=settings.auth_stub_enabled,
        oidc_verifier=verifier,
        claim_tenant=settings.oidc_claim_tenant,
        claim_roles=settings.oidc_claim_roles,
        claim_lang=settings.oidc_claim_lang,
        default_tenant_id=settings.default_tenant_id,
        default_user_id=settings.default_user_id,
        default_role=settings.default_user_role,
        default_lang=settings.default_language,
        supplied_tenant_id=request.query_params.get("tenant_id"),
    )
    set_request_context(
        trace_id=request.headers.get("x-trace-id"),
        request_id=request.headers.get("x-request-id"),
        tenant_id=claims["tenant_id"],
    )
    tenant_ctx = TenantContext(
        tenant_id=claims["tenant_id"],
        tenant_name=f"Tenant ({claims['tenant_id']})",
        isms_enforced=True,
    )
    user_ctx = UserContext(
        user_id=claims["user_id"],
        tenant_id=claims["tenant_id"],
        role=UserRole(claims["role"]),
        language=Language(claims["language"]),
        permissions=claims["permissions"],
        mfa_verified=bool(claims.get("mfa_verified", False)),
    )
    return tenant_ctx, user_ctx


async def get_tenant_context(
    contexts: tuple[TenantContext, UserContext] = Depends(get_current_contexts),
) -> TenantContext:
    """FastAPI dependency returning the current request's `TenantContext`."""
    return contexts[0]


async def get_user_context(
    contexts: tuple[TenantContext, UserContext] = Depends(get_current_contexts),
) -> UserContext:
    """FastAPI dependency returning the current request's `UserContext`."""
    return contexts[1]


def require_role(*allowed_roles: UserRole, require_step_up: bool = False):
    """Dependency factory enforcing RBAC role membership and optional step-up MFA on endpoints."""

    async def _checker(
        user: UserContext = Depends(get_user_context),
        settings: Settings = Depends(get_settings),
    ) -> UserContext:
        if user.role not in allowed_roles:
            raise AlbaError(code="UNAUTHORIZED", status_code=403, lang=user.language.value)
        if (require_step_up or settings.oidc_require_step_up_for_approvals) and not user.mfa_verified:
            raise AlbaError(code="UNAUTHORIZED", status_code=403, lang=user.language.value)
        return user

    return _checker
