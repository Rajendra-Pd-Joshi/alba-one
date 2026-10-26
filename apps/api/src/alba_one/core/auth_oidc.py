"""OIDC / JWKS JWT verification, step-up MFA checks, and dual-key S2S token rotation (Phase 10).

Uses `cryptography` (maintained PyCA library) for RS256 and ES256 JWS verification against
RFC 7517 JWKS endpoints, and `PyJWT[crypto]` when installed in the target runtime.
Never accepts `none` or HMAC (`HS*`) algorithms for OIDC tokens regardless of the header.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils

from alba_one.core.error_catalog import AlbaError

logger = logging.getLogger(__name__)

ALLOWED_ASYMMETRIC_ALGS: frozenset[str] = frozenset({"RS256", "ES256"})
FORBIDDEN_ALGS: frozenset[str] = frozenset({"none", "HS256", "HS384", "HS512"})


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwk_to_public_key(jwk: dict[str, Any]) -> rsa.RSAPublicKey | ec.EllipticCurvePublicKey:
    kty = jwk.get("kty")
    if kty == "RSA":
        n = int.from_bytes(_b64url_decode(jwk["n"]), "big")
        e = int.from_bytes(_b64url_decode(jwk["e"]), "big")
        return rsa.RSAPublicNumbers(e, n).public_key()
    if kty == "EC" and jwk.get("crv") == "P-256":
        x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
        y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
        return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    raise ValueError(f"Unsupported JWK kty/crv: {kty}/{jwk.get('crv')}")


def _verify_jws_signature(alg: str, signing_input: bytes, signature: bytes, jwk: dict[str, Any]) -> bool:
    pub_key = _jwk_to_public_key(jwk)
    try:
        if alg == "RS256" and isinstance(pub_key, rsa.RSAPublicKey):
            pub_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
            return True
        if alg == "ES256" and isinstance(pub_key, ec.EllipticCurvePublicKey) and len(signature) == 64:
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            pub_key.verify(utils.encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))
            return True
    except Exception:
        return False
    return False


@dataclass(frozen=True)
class OIDCConfig:
    """Configuration for enterprise OIDC JWT verification and JWKS caching."""

    issuer: str
    audience: str
    jwks_url: str
    allowed_algorithms: tuple[str, ...] = ("RS256", "ES256")
    leeway_seconds: int = 30
    max_token_age_seconds: int = 3600
    claim_tenant: str = "tenant_id"
    claim_roles: str = "roles"
    claim_lang: str = "lang"
    claim_token_use: str = "token_use"
    expected_token_use: str = "access"
    step_up_claim: str = "amr"
    step_up_values: tuple[str, ...] = ("mfa", "hwk", "otp", "webauthn")
    require_step_up_for_approvals: bool = False
    app_env: str = "production"
    jwks_ttl_seconds: int = 300
    jwks_max_stale_seconds: int = 3600
    jwks_min_refresh_interval_seconds: int = 30
    jwks_timeout_seconds: float = 3.0
    jwks_max_bytes: int = 65536


@dataclass
class JWKSCache:
    """Bounded TTL cache for JWKS keys with anti-amplification rate-limiting and stale fallback."""

    config: OIDCConfig
    fetcher: Callable[[str, float, int], bytes] | None = None
    _keys_by_kid: dict[str, dict[str, Any]] = field(default_factory=dict)
    _fetched_at: float = 0.0
    _last_refresh_attempt: float = 0.0
    stale_fallback_alert_count: int = 0

    def _default_fetch(self, url: str, timeout: float, max_bytes: int) -> bytes:
        if self.config.app_env != "development" and not url.lower().startswith("https://"):
            raise AlbaError(code="UNAUTHORIZED", status_code=503)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("JWKS response exceeded maximum size limit.")
            return data

    def _refresh(self, now: float, *, force: bool = False) -> None:
        if not force and (now - self._last_refresh_attempt) < self.config.jwks_min_refresh_interval_seconds:
            return
        self._last_refresh_attempt = now
        fetch_fn = self.fetcher or self._default_fetch
        try:
            raw = fetch_fn(self.config.jwks_url, self.config.jwks_timeout_seconds, self.config.jwks_max_bytes)
            keys = json.loads(raw.decode("utf-8")).get("keys", [])
            if not isinstance(keys, list) or not keys:
                raise ValueError("Empty or invalid JWKS keys array.")
            self._keys_by_kid = {str(k["kid"]): k for k in keys if isinstance(k, dict) and k.get("kid")}
            self._fetched_at = now
        except Exception as exc:
            logger.warning("jwks_refresh_failed", extra={"iss": self.config.issuer, "error_type": type(exc).__name__})
            age = now - self._fetched_at if self._fetched_at > 0 else float("inf")
            self.stale_fallback_alert_count += 1
            if self._keys_by_kid and age <= self.config.jwks_max_stale_seconds:
                return
            raise AlbaError(code="SERVICE_UNAVAILABLE", status_code=503) from exc

    def get_key(self, kid: str, *, now: float | None = None) -> dict[str, Any]:
        ts = time.time() if now is None else now
        if not self._keys_by_kid or (ts - self._fetched_at) > self.config.jwks_ttl_seconds:
            self._refresh(ts, force=not bool(self._keys_by_kid))
        if kid not in self._keys_by_kid:
            self._refresh(ts, force=False)
        if kid not in self._keys_by_kid:
            logger.warning("oidc_unknown_kid", extra={"kid": kid, "iss": self.config.issuer})
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        return self._keys_by_kid[kid]


class OIDCVerifier:
    """Verifies OIDC JWT access tokens and extracts tenant, role, and step-up MFA claims."""

    def __init__(self, config: OIDCConfig, jwks_cache: JWKSCache | None = None) -> None:
        self.config = config
        self.jwks_cache = jwks_cache or JWKSCache(config=config)

    def verify_access_token(self, raw_token: str, *, now: float | None = None) -> dict[str, Any]:
        ts = time.time() if now is None else now
        token = raw_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        parts = token.split(".")
        if len(parts) != 3:
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        try:
            header = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
            claims = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
            signature = _b64url_decode(parts[2])
        except Exception as exc:
            raise AlbaError(code="UNAUTHORIZED", status_code=401) from exc

        alg, kid = str(header.get("alg", "")), str(header.get("kid", ""))
        if (
            not alg
            or alg.lower() == "none"
            or alg.upper().startswith("HS")
            or alg in FORBIDDEN_ALGS
            or alg not in self.config.allowed_algorithms
            or alg not in ALLOWED_ASYMMETRIC_ALGS
            or not kid
        ):
            logger.warning("oidc_rejected_alg_or_kid", extra={"alg": alg, "kid": kid})
            raise AlbaError(code="UNAUTHORIZED", status_code=401)

        jwk = self.jwks_cache.get_key(kid, now=ts)
        if jwk.get("alg") and jwk["alg"] != alg:
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        if not _verify_jws_signature(alg, f"{parts[0]}.{parts[1]}".encode("ascii"), signature, jwk):
            logger.warning("oidc_invalid_signature", extra={"kid": kid, "iss": self.config.issuer})
            raise AlbaError(code="UNAUTHORIZED", status_code=401)

        self._validate_standard_claims(header, claims, ts)
        return claims

    def _validate_standard_claims(self, header: dict[str, Any], claims: dict[str, Any], now: float) -> None:
        if claims.get("iss") != self.config.issuer:
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        aud = claims.get("aud")
        aud_list = [aud] if isinstance(aud, str) else (aud if isinstance(aud, list) else [])
        if self.config.audience not in aud_list or not str(claims.get("sub") or "").strip():
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        exp, nbf, iat = claims.get("exp"), claims.get("nbf"), claims.get("iat")
        if not isinstance(exp, (int, float)) or (now - self.config.leeway_seconds) >= float(exp):
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        if isinstance(nbf, (int, float)) and (now + self.config.leeway_seconds) < float(nbf):
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        if isinstance(iat, (int, float)):
            if (now + self.config.leeway_seconds) < float(iat) or (now - float(iat)) > (
                self.config.max_token_age_seconds + self.config.leeway_seconds
            ):
                raise AlbaError(code="UNAUTHORIZED", status_code=401)
        typ = str(header.get("typ", "")).lower()
        token_use = str(claims.get(self.config.claim_token_use, "")).lower()
        if token_use == "id" or typ == "id_token":
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        if token_use and self.config.expected_token_use and token_use != self.config.expected_token_use:
            raise AlbaError(code="UNAUTHORIZED", status_code=401)

    def check_step_up_mfa(self, claims: dict[str, Any]) -> bool:
        raw = claims.get(self.config.step_up_claim)
        values = [raw] if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
        return bool({str(v).lower() for v in values}.intersection({v.lower() for v in self.config.step_up_values}))


@dataclass(frozen=True)
class InternalBearerRotator:
    """Dual-key internal S2S token authenticator supporting zero-downtime secret rotation."""

    current_secret: str
    previous_secret: str = ""
    previous_secret_expires_at: float = 0.0
    token_ttl_seconds: int = 60

    def issue_s2s_token(self, *, tenant_id: str, user_id: str, role: str, now: float | None = None) -> str:
        ts = int(time.time() if now is None else now)
        payload = {"tenant_id": tenant_id, "sub": user_id, "role": role, "iat": ts, "exp": ts + self.token_ttl_seconds}
        body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        sig = hmac.new(self.current_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        return f"s2s.{body}.{_b64url_encode(sig)}"

    def verify_s2s_token(self, token: str, *, now: float | None = None) -> dict[str, Any]:
        ts = time.time() if now is None else now
        cleaned = token.strip()
        if cleaned.lower().startswith("bearer "):
            cleaned = cleaned[7:].strip()
        parts = cleaned.split(".")
        if len(parts) != 3 or parts[0] != "s2s":
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        body, provided_sig = parts[1], _b64url_decode(parts[2])
        secrets = [self.current_secret]
        if self.previous_secret and (self.previous_secret_expires_at <= 0 or ts <= self.previous_secret_expires_at):
            secrets.append(self.previous_secret)
        if not any(
            sec and hmac.compare_digest(provided_sig, hmac.new(sec.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
            for sec in secrets
        ):
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        claims = json.loads(_b64url_decode(body).decode("utf-8"))
        if float(claims.get("exp", 0)) <= ts:
            raise AlbaError(code="UNAUTHORIZED", status_code=401)
        return claims
