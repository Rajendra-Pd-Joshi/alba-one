"""Phase 10 unit tests: OIDC/JWKS auth, step-up MFA, S2S dual-secret rotation, startup fail-closed checks, and config secret scanning."""

from __future__ import annotations

import json
import math
import subprocess
import unittest
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils

from alba_one.core.auth_oidc import (
    InternalBearerRotator,
    JWKSCache,
    OIDCConfig,
    OIDCVerifier,
    _b64url_encode,
)
from alba_one.core.error_catalog import AlbaError
from alba_one.core.startup_checks import (
    StartupSecurityCheckError,
    enforce_startup_checks,
    evaluate_startup_environment,
)
from alba_one.core.tenancy_logic import resolve_auth_claims

REPO_ROOT = Path(__file__).resolve().parents[4]

def _int_to_b64url(val: int, length: int | None = None) -> str:
    byte_len = length or max(1, (val.bit_length() + 7) // 8)
    return _b64url_encode(val.to_bytes(byte_len, "big"))

def _make_rsa_jwk(priv_key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    nums = priv_key.public_key().public_numbers()
    return {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid, "n": _int_to_b64url(nums.n), "e": _int_to_b64url(nums.e)}

def _make_ec_jwk(priv_key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    nums = priv_key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "use": "sig", "alg": "ES256", "kid": kid, "x": _int_to_b64url(nums.x, 32), "y": _int_to_b64url(nums.y, 32)}

def _sign_jws(header: dict[str, Any], payload: dict[str, Any], priv_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey | bytes) -> str:
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    alg = header.get("alg")
    if alg == "RS256" and isinstance(priv_key, rsa.RSAPrivateKey):
        sig = priv_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    elif alg == "ES256" and isinstance(priv_key, ec.EllipticCurvePrivateKey):
        der = priv_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    elif alg == "none":
        sig = b""
    else:
        sig = b"forged-hmac-signature"
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"

def _valid_prod_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "AUTH_STUB_ENABLED": "false",
        "OIDC_ISSUER": "https://idp.albaconnect.co.jp/oauth2/default",
        "OIDC_AUDIENCE": "api://alba-one",
        "OIDC_JWKS_URL": "https://idp.albaconnect.co.jp/oauth2/default/v1/keys",
        "DEBUG": "false",
        "RELOAD": "false",
        "OPENAPI_DOCS_ENABLED": "false",
        "CORS_ALLOWED_ORIGINS": "https://alba-one.albaconnect.co.jp",
        "CORS_ALLOW_CREDENTIALS": "true",
        "GATEWAY_API_KEY": "pk-live-prod-key-99887766",
        "OPENAI_API_KEY": "sk-live-prod-key-11223344",
        "PINECONE_API_KEY": "pc-live-prod-key-55667788",
        "COHERE_API_KEY": "co-live-prod-key-44332211",
        "INTERNAL_S2S_CURRENT_SECRET": "s2s-live-prod-secret-key-aabbccddeeff0011",
        "DATABASE_URL": "postgresql+psycopg://alba_app@rds.internal:5432/alba_one?sslmode=verify-full",
        "REDIS_URL": "rediss://:redis-live-prod-pass-9900@redis.internal:6379/0",
        "TRACE_CAPTURE_CONTENT": "false",
        "BEDROCK_GUARDRAIL_ID": "gr-prod-998877",
        "BEDROCK_GUARDRAIL_VERSION": "2",
        "BEDROCK_GUARDRAIL_TIER": "STANDARD",
        "OPS_KILL_SWITCH": "false",
        "GUARDRAIL_MODE": "enforce",
        "FETCH_DOMAIN_POLICY": "denylist",
        "OUTBOUND_QUERY_POLICY": "block",
    }

class TestPhase10OIDCAndJWKS(unittest.TestCase):
    """Tests for RS256/ES256 JWT verification, JWKS rate-limiting/stale fallback, and claim mapping."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.ec_key = ec.generate_private_key(ec.SECP256R1())
        cls.jwks_doc = {"keys": [_make_rsa_jwk(cls.rsa_key, "kid-rsa-1"), _make_ec_jwk(cls.ec_key, "kid-ec-1")]}
        cls.cfg = OIDCConfig(
            issuer="https://idp.albaconnect.co.jp",
            audience="api://alba-one",
            jwks_url="https://idp.albaconnect.co.jp/.well-known/jwks.json",
            require_step_up_for_approvals=True,
        )

    def _make_verifier(self, fetch_fn=None) -> tuple[OIDCVerifier, list[float]]:
        calls: list[float] = []

        def _default_fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
            calls.append(1.0)
            return json.dumps(self.jwks_doc).encode("utf-8")

        cache = JWKSCache(config=self.cfg, fetcher=fetch_fn or _default_fetcher)
        return OIDCVerifier(config=self.cfg, jwks_cache=cache), calls

    def test_rs256_and_es256_tokens_accepted(self) -> None:
        verifier, _ = self._make_verifier()
        now = 1_700_000_000.0
        base_claims = {
            "iss": "https://idp.albaconnect.co.jp",
            "aud": ["api://alba-one"],
            "sub": "user_approver_01",
            "tenant_id": "tenant_alba_demo",
            "roles": ["unknown_custom_role", "approver"],
            "lang": "ja",
            "amr": ["pwd", "mfa"],
            "token_use": "access",
            "iat": int(now - 60),
            "nbf": int(now - 60),
            "exp": int(now + 600),
        }
        rsa_tok = _sign_jws({"alg": "RS256", "kid": "kid-rsa-1", "typ": "JWT"}, base_claims, self.rsa_key)
        ec_tok = _sign_jws({"alg": "ES256", "kid": "kid-ec-1", "typ": "JWT"}, base_claims, self.ec_key)
        c1 = verifier.verify_access_token(rsa_tok, now=now)
        c2 = verifier.verify_access_token(ec_tok, now=now)
        self.assertEqual(c1["sub"], "user_approver_01")
        self.assertEqual(c2["tenant_id"], "tenant_alba_demo")
        self.assertTrue(verifier.check_step_up_mfa(c1))

    def test_rejects_none_hmac_expired_wrong_iss_aud_and_id_token(self) -> None:
        verifier, _ = self._make_verifier()
        now = 1_700_000_000.0
        valid = {"iss": "https://idp.albaconnect.co.jp", "aud": "api://alba-one", "sub": "u1", "tenant_id": "t1", "roles": ["analyst"], "iat": int(now - 10), "exp": int(now + 300)}
        for hdr, claims, key in [
            ({"alg": "none", "kid": "kid-rsa-1"}, valid, b""),
            ({"alg": "HS256", "kid": "kid-rsa-1"}, valid, b"secret"),
            ({"alg": "RS256", "kid": "kid-rsa-1"}, {**valid, "exp": int(now - 120)}, self.rsa_key),
            ({"alg": "RS256", "kid": "kid-rsa-1"}, {**valid, "iat": int(now - 7200)}, self.rsa_key),
            ({"alg": "RS256", "kid": "kid-rsa-1"}, {**valid, "token_use": "id"}, self.rsa_key),
        ]:
            with self.assertRaises(AlbaError):
                verifier.verify_access_token(_sign_jws(hdr, claims, key), now=now)

    def test_jwks_unknown_kid_anti_amplification_and_stale_fallback(self) -> None:
        should_fail, fetch_count = False, 0

        def _fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
            nonlocal fetch_count
            fetch_count += 1
            if should_fail:
                raise ConnectionError("IdP unreachable")
            return json.dumps(self.jwks_doc).encode("utf-8")

        verifier, _ = self._make_verifier(_fetcher)
        now = 1_700_000_000.0
        claims = {"iss": "https://idp.albaconnect.co.jp", "aud": "api://alba-one", "sub": "u1", "tenant_id": "t1", "roles": ["analyst"], "iat": int(now), "exp": int(now + 900)}
        good_tok = _sign_jws({"alg": "RS256", "kid": "kid-rsa-1"}, claims, self.rsa_key)
        verifier.verify_access_token(good_tok, now=now)
        self.assertEqual(fetch_count, 1)

        for i in range(5):
            with self.assertRaises(AlbaError):
                verifier.verify_access_token(_sign_jws({"alg": "RS256", "kid": f"rnd-{i}"}, claims, self.rsa_key), now=now + 5)
        self.assertEqual(fetch_count, 1)

        should_fail = True
        verifier.verify_access_token(good_tok, now=now + 400)
        self.assertEqual(verifier.jwks_cache.stale_fallback_alert_count, 1)

        late_tok = _sign_jws({"alg": "RS256", "kid": "kid-rsa-1"}, {**claims, "iat": int(now + 4000), "exp": int(now + 4300)}, self.rsa_key)
        with self.assertRaises(AlbaError) as ctx:
            verifier.verify_access_token(late_tok, now=now + 4000)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_stub_headers_ignored_when_stub_disabled_and_conflicting_tenant_rejected(self) -> None:
        verifier, _ = self._make_verifier()
        with self.assertRaises(AlbaError) as ctx:
            resolve_auth_claims({"X-Tenant-Id": "t_atk", "X-User-Id": "u_atk", "X-User-Role": "admin", "X-Auth-Stub-Enabled": "true"}, stub_enabled=False, oidc_verifier=verifier)
        self.assertEqual(ctx.exception.status_code, 401)

        verifier.verify_access_token = lambda tok: {"sub": "u1", "roles": ["analyst"]}  # type: ignore[method-assign]
        with self.assertRaises(AlbaError) as ctx2:
            resolve_auth_claims({"Authorization": "Bearer valid"}, stub_enabled=False, oidc_verifier=verifier)
        self.assertEqual(ctx2.exception.status_code, 403)

        verifier.verify_access_token = lambda tok: {"sub": "u1", "tenant_id": "tenant_real", "roles": ["unknown", "analyst"], "amr": ["mfa"]}  # type: ignore[method-assign]
        with self.assertRaises(AlbaError) as ctx3:
            resolve_auth_claims({"Authorization": "Bearer valid", "X-Tenant-Id": "tenant_spoof"}, stub_enabled=False, oidc_verifier=verifier)
        self.assertEqual(ctx3.exception.status_code, 403)

class TestPhase10DualSecretRotationAndStartupChecks(unittest.TestCase):
    """Tests for dual-secret S2S rotation, fail-closed startup checks, and config secret hygiene."""

    def test_internal_bearer_rotator_accepts_current_and_previous_within_window(self) -> None:
        now = 1_700_000_000.0
        old_rot = InternalBearerRotator(current_secret="secret-v1-old")
        new_rot = InternalBearerRotator(current_secret="secret-v2-new", previous_secret="secret-v1-old", previous_secret_expires_at=now + 3600)
        third_rot = InternalBearerRotator(current_secret="secret-v0-ancient")

        t1 = old_rot.issue_s2s_token(tenant_id="t1", user_id="u1", role="analyst", now=now)
        t2 = new_rot.issue_s2s_token(tenant_id="t1", user_id="u1", role="analyst", now=now)
        t0 = third_rot.issue_s2s_token(tenant_id="t1", user_id="u1", role="analyst", now=now)

        self.assertEqual(new_rot.verify_s2s_token(t2, now=now + 10)["tenant_id"], "t1")
        self.assertEqual(new_rot.verify_s2s_token(t1, now=now + 10)["tenant_id"], "t1")
        with self.assertRaises(AlbaError):
            new_rot.verify_s2s_token(t0, now=now + 10)
        t1_late = old_rot.issue_s2s_token(tenant_id="t1", user_id="u1", role="analyst", now=now + 3700)
        with self.assertRaises(AlbaError):
            new_rot.verify_s2s_token(t1_late, now=now + 3710)

    def test_unset_or_unknown_app_env_treated_as_production_strict(self) -> None:
        env = _valid_prod_env()
        del env["APP_ENV"]
        with self.assertRaises(StartupSecurityCheckError) as ctx:
            enforce_startup_checks(env)
        self.assertEqual(ctx.exception.effective_env, "production")

        env["APP_ENV"] = "prod_typo"
        with self.assertRaises(StartupSecurityCheckError) as ctx2:
            enforce_startup_checks(env)
        self.assertEqual(ctx2.exception.effective_env, "production")

    def test_startup_checks_collect_every_violation_at_once(self) -> None:
        bad_env = {
            "APP_ENV": "production",
            "AUTH_STUB_ENABLED": "true",
            "OIDC_ISSUER": "http://insecure.idp.local",
            "OIDC_AUDIENCE": "",
            "OIDC_JWKS_URL": "",
            "DEBUG": "true",
            "OPENAPI_DOCS_ENABLED": "true",
            "CORS_ALLOWED_ORIGINS": "*",
            "CORS_ALLOW_CREDENTIALS": "true",
            "GATEWAY_API_KEY": "replace-with-portkey-api-key",
            "OPENAI_API_KEY": "replace-with-openai-api-key",
            "PINECONE_API_KEY": "replace-with-pinecone-api-key",
            "COHERE_API_KEY": "replace-with-cohere-api-key",
            "INTERNAL_S2S_CURRENT_SECRET": "replace-with-internal-s2s-secret",
            "DATABASE_URL": "postgresql+psycopg://alba:alba_dev_password@localhost:5432/alba_one",
            "REDIS_URL": "redis://localhost:6379/0",
            "TRACE_CAPTURE_CONTENT": "true",
            "BEDROCK_GUARDRAIL_ID": "replace-with-bedrock-guardrail-id",
            "BEDROCK_GUARDRAIL_VERSION": "1",
            "BEDROCK_GUARDRAIL_TIER": "CLASSIC",
            "GUARDRAIL_MODE": "monitor",
            "FETCH_DOMAIN_POLICY": "open_public",
            "OUTBOUND_QUERY_POLICY": "generalize",
        }
        with self.assertRaises(StartupSecurityCheckError) as ctx:
            enforce_startup_checks(bad_env)
        self.assertGreaterEqual(len(ctx.exception.violations), 15)

    def test_valid_prod_env_passes_and_surfaces_admin_warnings(self) -> None:
        env = _valid_prod_env()
        env["GUARDRAIL_MODE"] = "monitor"
        env["ALLOW_GUARDRAIL_MONITOR_IN_PROD"] = "true"
        report = evaluate_startup_environment(env, unreviewed_goldens_count=12, unset_thresholds_count=4, unpriced_models=["custom-v1"])
        self.assertEqual(report.violations, [])
        self.assertEqual(len(report.warnings), 4)

    def test_check_images_script_and_committed_config_secret_hygiene(self) -> None:

        for folder in ("config", "deploy"):
            for path in (REPO_ROOT / folder).rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                for pref in ("sk-proj-", "sk-live-", "pcsk_", "ghp_", "AKIA"):
                    self.assertNotIn(pref, text)
                for line in text.splitlines():
                    if line.lstrip().startswith("#"):
                        continue
                    for tok in line.split():
                        c = tok.strip("\"',;")
                        if c.isascii() and len(c) >= 40 and "/" not in c and ":" not in c and "." not in c:
                            probs = [c.count(ch) / len(c) for ch in set(c)]
                            self.assertLess(-sum(p * math.log2(p) for p in probs), 4.5, f"High entropy in {path}")

if __name__ == "__main__":
    unittest.main()
