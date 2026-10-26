"""Unit tests for Web Search SSRF Fetcher, Outbound Query Guardrail, MCP Client & Evals (`test_web_search_and_outbound_guard.py`)."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.guardrails.outbound_query import check_outbound_query
from alba_one.guardrails.types import GuardrailContext
from alba_one.mcp_client.client import (
    MCPExternalSearchAdapter,
    build_multiserver_mcp_config,
    discover_registered_tools,
)
from alba_one.mcp_servers.web_search.fetcher import (
    fetch_page_safely,
    validate_url_ssrf_and_domain_policy,
)
from evals.mcp.engine import evaluate_server, load_mcp_golden


class _FakeHTTPResponse:
    def __init__(self, status_code: int, content: bytes, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTPClient:
    def __init__(self, responses: list[_FakeHTTPResponse]) -> None:
        self._responses = list(responses)

    def get(self, url: str, follow_redirects: bool = False) -> _FakeHTTPResponse:
        return self._responses.pop(0)

    def close(self) -> None:
        pass


class TestWebSearchSSRFAndOutboundGuard(unittest.TestCase):
    """Test outbound query DLP, SSRF DNS & redirect protection, MCP client, and eval draft gate."""

    def setUp(self) -> None:
        self.ctx = GuardrailContext(tenant_id="tenant_alba_demo", lang="ja")

    def test_outbound_query_blocks_sensitive_codename_without_logging_term(self) -> None:
        raw_query = "PROJECT-KAGUYA 東都製薬株式会社 リーファー遅延対策"
        res = check_outbound_query(raw_query, self.ctx, policy_mode="block")
        self.assertEqual(res.action, "block")
        self.assertEqual(res.policy, "outbound_query_sensitive_term_blocked")
        serialized_details = json.dumps(res.details, ensure_ascii=False)
        self.assertNotIn("PROJECT-KAGUYA", serialized_details)
        self.assertNotIn("東都製薬株式会社", serialized_details)
        self.assertGreaterEqual(res.details["sensitive_term_count"], 2)

    def test_outbound_query_generalizes_sensitive_terms_and_scrubs_pii(self) -> None:
        raw_query = "Contact 090-1234-5678 about PROJECT-KAGUYA and 東都製薬株式会社"
        res = check_outbound_query(raw_query, self.ctx, policy_mode="generalize")
        self.assertEqual(res.action, "mask")
        cleaned = str(res.sanitized_payload)
        self.assertNotIn("PROJECT-KAGUYA", cleaned)
        self.assertNotIn("東都製薬株式会社", cleaned)
        self.assertNotIn("090-1234-5678", cleaned)
        self.assertIn("次世代港湾自動化システム", cleaned)
        self.assertIn("国内大手製薬メーカー", cleaned)

        secret_res = check_outbound_query("query api_key=sk-1234567890abcdef12345678", self.ctx, policy_mode="generalize")
        self.assertEqual(secret_res.action, "block")
        self.assertEqual(secret_res.policy, "outbound_query_secret_blocked")

    def test_ssrf_blocks_private_loopback_and_cloud_metadata_ips(self) -> None:
        with self.assertRaises(PermissionError):
            validate_url_ssrf_and_domain_policy(
                "http://169.254.169.254/latest/meta-data/",
                dns_resolver=lambda h: ["169.254.169.254"],
            )
        with self.assertRaises(PermissionError):
            validate_url_ssrf_and_domain_policy(
                "https://evil-rebind.example.com/data",
                dns_resolver=lambda h: ["10.0.14.22"],
            )

    def test_fetch_page_safely_rechecks_redirect_target_ssrf(self) -> None:
        fake_client = _FakeHTTPClient(
            [
                _FakeHTTPResponse(
                    302,
                    b"",
                    {"location": "https://rebind-redirect.example.com/iam"},
                )
            ]
        )

        def resolver(host: str) -> list[str]:
            return ["169.254.169.254"] if "rebind" in host else ["93.184.216.34"]

        with self.assertRaises(PermissionError) as ctx:
            fetch_page_safely(
                "https://www.jma.go.jp/bosai/warning/",
                dns_resolver=resolver,
                http_client=fake_client,  # type: ignore[arg-type]
            )
        self.assertIn("SSRF blocked", str(ctx.exception))

    def test_fetch_page_safely_extracts_html_and_scrubs_pii(self) -> None:
        html = (
            b"<html><head><script>alert(1)</script></head>"
            b"<body><h1>Tokyo Port Advisory</h1><p>Call 03-1234-5678 for port captain.</p></body></html>"
        )
        fake_client = _FakeHTTPClient(
            [_FakeHTTPResponse(200, html, {"content-type": "text/html; charset=utf-8"})]
        )
        out = fetch_page_safely(
            "https://www.jma.go.jp/bosai/warning/",
            dns_resolver=lambda h: ["93.184.216.34"],
            http_client=fake_client,  # type: ignore[arg-type]
        )
        self.assertTrue(out["external"])
        self.assertIn("Tokyo Port Advisory", out["text"])
        self.assertNotIn("alert(1)", out["text"])
        self.assertNotIn("03-1234-5678", out["text"])

    def test_mcp_client_discovery_and_external_search_adapter(self) -> None:
        all_tools = discover_registered_tools()
        self.assertEqual(len(all_tools), 43)
        cfg = build_multiserver_mcp_config(profile_filter="core")
        self.assertIn("knowledge_base", cfg)
        self.assertIn("sql_readonly", cfg)

        adapter = MCPExternalSearchAdapter(tenant_id="tenant_alba_demo")
        ext_hits = adapter.search_external("東京港 PROJECT-KAGUYA 強風", lang="ja")
        self.assertGreaterEqual(len(ext_hits), 2)
        self.assertTrue(all(h.external for h in ext_hits))

    def test_mcp_eval_engine_refuses_draft_without_flag(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            load_mcp_golden("web_search", allow_draft=False)
        self.assertIn("--allow-draft", str(ctx.exception))

        report = evaluate_server("web_search", allow_draft=True)
        self.assertEqual(report["items_evaluated"], 16)
        self.assertEqual(report["metrics"]["ToolCorrectnessMetric"], 1.0)
        self.assertEqual(report["metrics"]["NegativeAbstentionRate"], 1.0)


if __name__ == "__main__":
    unittest.main()
