"""Unit tests for tenancy/RBAC stub, structured JSON logging, bilingual errors, and gateway routing."""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl, sys as _sys
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import base64
import json
import logging
import unittest

from alba_one.core.error_catalog import AlbaError
from alba_one.core.logging import StructuredJSONFormatter, set_request_context
from alba_one.core.tenancy_logic import resolve_auth_claims
from alba_one.gateway.routing import (
    GatewayCallMetadata,
    build_gateway_headers,
    resolve_fallback_chain,
)


def _encode_jwt(payload: dict[str, str]) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


class TestTenancyLoggingAndGateway(unittest.TestCase):
    """Verify Principle 6 (gateway swapping), Principle 7 (bilingual errors), and Principle 8 (tenancy)."""

    def test_jwt_and_stub_header_resolution_and_cross_tenant_rejection(self) -> None:
        token = _encode_jwt(
            {
                "sub": "user_approver_01",
                "tenant_id": "tenant_alba_demo",
                "role": "approver",
                "lang": "ja",
            }
        )
        claims = resolve_auth_claims({"Authorization": f"Bearer {token}"}, stub_enabled=True)
        self.assertEqual(claims["tenant_id"], "tenant_alba_demo")
        self.assertEqual(claims["role"], "approver")
        self.assertIn("decisions:approve", claims["permissions"])

        # Cross-tenant header mismatch must raise TENANT_MISMATCH (403)
        with self.assertRaises(AlbaError) as ctx:
            resolve_auth_claims(
                {
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant_intruder",
                },
                stub_enabled=True,
            )
        self.assertEqual(ctx.exception.code, "TENANT_MISMATCH")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bilingual_error_payload_includes_ja_en_and_trace_id(self) -> None:
        err = AlbaError(
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            lang="ja",
            params={"retry_after": 12},
        )
        payload = err.to_dict(trace_id="tr_test_999")
        self.assertEqual(payload["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertIn("12秒後", payload["error"]["message_ja"])
        self.assertIn("12 seconds", payload["error"]["message_en"])
        self.assertEqual(payload["error"]["trace_id"], "tr_test_999")

    def test_structured_json_logger_embeds_trace_and_tenant_ids(self) -> None:
        set_request_context(
            trace_id="tr_abc123",
            request_id="req_def456",
            tenant_id="tenant_alba_demo",
        )
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="alba_one",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Test decision log",
            args=(),
            exc_info=None,
        )
        rendered = json.loads(formatter.format(record))
        self.assertEqual(rendered["trace_id"], "tr_abc123")
        self.assertEqual(rendered["request_id"], "req_def456")
        self.assertEqual(rendered["tenant_id"], "tenant_alba_demo")

    def test_gateway_headers_swappable_across_portkey_bifrost_tensorzero_mesh(self) -> None:
        meta = GatewayCallMetadata(
            tenant_id="tenant_alba_demo",
            task="hypothesis_generation",
            prompt_version="hyp_v1.2",
            trace_id="tr_001",
        )
        for provider, expected_header in [
            ("portkey", "x-portkey-metadata"),
            ("bifrost", "x-bf-metadata"),
            ("tensorzero", "x-tensorzero-tags"),
            ("mesh", "x-mesh-metadata"),
        ]:
            headers = build_gateway_headers(
                provider=provider,
                gateway_api_key="gw-key",
                metadata=meta,
                fallback_models=["gpt-4o-mini-2024-07-18"],
                primary_model="gpt-4o-2024-08-06",
            )
            self.assertIn(expected_header, headers)
            self.assertEqual(headers["x-alba-tenant-id"], "tenant_alba_demo")
            self.assertEqual(headers["x-alba-task"], "hypothesis_generation")
            self.assertEqual(headers["x-alba-prompt-version"], "hyp_v1.2")

        chain = resolve_fallback_chain(
            "gpt-4o-2024-08-06",
            ["gpt-4o-mini-2024-07-18", "gpt-4o-2024-08-06"],
        )
        self.assertEqual(chain, ["gpt-4o-2024-08-06", "gpt-4o-mini-2024-07-18"])


if __name__ == "__main__":
    unittest.main()
