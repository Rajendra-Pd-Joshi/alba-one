"""Pure RBAC, OIDC claim mapping, and tenant isolation logic (stdlib + core/auth_oidc).

Separated from FastAPI dependency glue so it can be unit-tested with `unittest`.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from alba_one.core.auth_oidc import OIDCVerifier
from alba_one.core.error_catalog import AlbaError

logger = logging.getLogger(__name__)

VALID_ROLES: frozenset[str] = frozenset(
    {"viewer", "analyst", "approver", "knowledge_steward", "admin"}
)
ROLE_PRIORITY: tuple[str, ...] = (
    "admin",
    "approver",
    "knowledge_steward",
    "analyst",
    "viewer",
)

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "viewer": ["decisions:read", "kb:read", "outcomes:read"],
    "analyst": [
        "decisions:read",
        "decisions:create",
        "kb:read",
        "tools:invoke_readonly",
        "outcomes:read",
    ],
    "knowledge_steward": [
        "decisions:read",
        "kb:read",
        "kb:writeback",
        "outcomes:read",
        "outcomes:review",
    ],
    "approver": [
        "decisions:read",
        "decisions:create",
        "decisions:approve",
        "kb:read",
        "kb:writeback",
        "tools:invoke_readonly",
        "tools:approve_side_effect",
        "outcomes:read",
        "outcomes:review",
    ],
    "admin": [
        "decisions:read",
        "decisions:create",
        "decisions:approve",
        "kb:read",
        "kb:writeback",
        "kb:admin",
        "tools:invoke_readonly",
        "tools:approve_side_effect",
        "outcomes:read",
        "outcomes:review",
        "guardrails:admin",
        "evals:run",
    ],
}


def decode_stub_jwt_claims(bearer_token: str) -> dict[str, Any]:
    """# STUB: Decode an unverified JWT payload ONLY when `AUTH_STUB_ENABLED=true` in dev/test."""
    token = bearer_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise AlbaError(code="UNAUTHORIZED", status_code=401)

    parts = token.split(".")
    if len(parts) == 3:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        try:
            decoded_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
            claims = json.loads(decoded_bytes.decode("utf-8"))
            if isinstance(claims, dict):
                return claims
        except Exception as exc:
            raise AlbaError(code="UNAUTHORIZED", status_code=401) from exc

    raise AlbaError(code="UNAUTHORIZED", status_code=401)


def _extract_verified_role(raw_roles: Any) -> str:
    """Select the highest-privilege known role from OIDC claims; drop unknown roles."""
    if isinstance(raw_roles, str):
        candidates = [r.strip().lower() for r in raw_roles.split(",") if r.strip()]
    elif isinstance(raw_roles, list):
        candidates = [str(r).strip().lower() for r in raw_roles if str(r).strip()]
    else:
        candidates = []
    known = [r for r in candidates if r in VALID_ROLES]
    if not known:
        return ""
    for prio in ROLE_PRIORITY:
        if prio in known:
            return prio
    return known[0]


def resolve_auth_claims(
    headers: dict[str, str],
    *,
    stub_enabled: bool = False,
    oidc_verifier: OIDCVerifier | None = None,
    claim_tenant: str = "tenant_id",
    claim_roles: str = "roles",
    claim_lang: str = "lang",
    default_tenant_id: str = "tenant_alba_demo",
    default_user_id: str = "user_analyst_01",
    default_role: str = "analyst",
    default_lang: str = "ja",
    supplied_tenant_id: str | None = None,
) -> dict[str, Any]:
    """Resolve `tenant_id`, `user_id`, `role`, `language`, `permissions`, and `mfa_verified`.

    - When `stub_enabled=False` (production/staging default), dev headers (`x-user-id`,
      `x-user-role`, `x-tenant-id`) can NEVER authenticate a request or override claims,
      and a request cannot enable the stub via headers.
    - In OIDC mode, `tenant_id` and `roles` come strictly from the verified JWT.
      Unknown roles are dropped; missing tenant claim -> 403; conflicting tenant id -> 403 + security event.
    """
    normalized = {k.lower(): v.strip() for k, v in headers.items() if v}
    auth_header = normalized.get("authorization", "")
    mfa_verified = False

    if not stub_enabled:
        if not auth_header or oidc_verifier is None:
            raise AlbaError(code="UNAUTHORIZED", status_code=401, lang=default_lang)
        claims = oidc_verifier.verify_access_token(auth_header)
        tenant_id = str(claims.get(claim_tenant, "")).strip()
        user_id = str(claims.get("sub") or "").strip()
        raw_roles = claims.get(claim_roles) if claim_roles in claims else claims.get("role")
        role = _extract_verified_role(raw_roles)
        lang = str(claims.get(claim_lang, default_lang)).strip().lower()
        mfa_verified = oidc_verifier.check_step_up_mfa(claims)
    else:
        if auth_header:
            claims = (
                oidc_verifier.verify_access_token(auth_header)
                if oidc_verifier is not None
                else decode_stub_jwt_claims(auth_header)
            )
            tenant_id = str(claims.get(claim_tenant) or claims.get("tenant_id") or "").strip()
            user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
            raw_roles = claims.get(claim_roles) if claim_roles in claims else claims.get("role", "viewer")
            role = _extract_verified_role(raw_roles)
            lang = str(claims.get(claim_lang, default_lang)).strip().lower()
            mfa_verified = bool(claims.get("mfa_verified", False))
        else:
            tenant_id = normalized.get("x-tenant-id", default_tenant_id)
            user_id = normalized.get("x-user-id", default_user_id)
            role = _extract_verified_role(normalized.get("x-user-role", default_role))
            lang = normalized.get("x-lang", default_lang).lower()
            mfa_verified = normalized.get("x-mfa-verified", "false").lower() == "true"

    if lang not in ("ja", "en"):
        lang = "ja"

    if not tenant_id:
        logger.warning("security_event_missing_tenant_claim", extra={"user_id": user_id})
        raise AlbaError(code="TENANT_MISMATCH", status_code=403, lang=lang)

    for candidate in (normalized.get("x-tenant-id"), supplied_tenant_id):
        if candidate and candidate.strip() != tenant_id:
            logger.warning(
                "security_event_conflicting_tenant_id",
                extra={"token_tenant_id": tenant_id, "supplied_tenant_id": candidate.strip()},
            )
            raise AlbaError(code="TENANT_MISMATCH", status_code=403, lang=lang)

    if not user_id or role not in VALID_ROLES:
        raise AlbaError(code="UNAUTHORIZED", status_code=401, lang=lang)

    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
        "language": lang,
        "permissions": list(ROLE_PERMISSIONS[role]),
        "mfa_verified": mfa_verified,
    }
