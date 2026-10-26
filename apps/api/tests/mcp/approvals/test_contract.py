"""Contract test suite for MCP server `approvals` (`tests/mcp/approvals/test_contract.py`).

Verifies:
1. Schema validation on valid & missing required arguments.
2. Bearer token authentication rejection (`MCPAuthError`).
3. Timeout enforcement (`TimeoutError`).
4. `tool_calls` audit log population (`ToolCallAuditEntry`).
"""

from __future__ import annotations

from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parents[2] / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.mcp_servers.base import MCPAuthError, MCPToolExecutionError
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool


class TestMCPContract_approvals(unittest.TestCase):
    """Contract tests for `approvals` (`write` class, profile `domain`)."""

    def test_valid_call_and_audit_log(self) -> None:
        rt = get_server_runtime("approvals")
        before_count = len(rt.audit_log)
        args = {'tenant_id': 'tenant_alba_demo', 'decision_id': 'dec_demo_001', 'lang': 'ja'}
        res = invoke_mcp_tool(
            "approvals",
            "request_approval",
            args,
            bearer_token="dev-mcp-token",
            approval_id="apr_contract_001",
            user_confirmed=True,
        )
        self.assertEqual(res["mcp_server"], "approvals")
        self.assertEqual(res["tool_name"], "request_approval")
        self.assertEqual(res["tool_class"], "write")
        self.assertIn("data", res)
        self.assertEqual(len(rt.audit_log), before_count + 1)

    def test_missing_required_args_blocked(self) -> None:
        with self.assertRaises(MCPToolExecutionError) as ctx:
            invoke_mcp_tool(
                "approvals",
                "request_approval",
                {},
                bearer_token="dev-mcp-token",
                approval_id="apr_contract_001",
                user_confirmed=True,
            )
        self.assertIn("SCHEMA", ctx.exception.code)

    def test_invalid_bearer_token_rejected(self) -> None:
        args = {'tenant_id': 'tenant_alba_demo', 'decision_id': 'dec_demo_001', 'lang': 'ja'}
        with self.assertRaises(MCPAuthError):
            invoke_mcp_tool(
                "approvals",
                "request_approval",
                args,
                bearer_token="wrong-secret-token",
                approval_id="apr_contract_001",
            )

    def test_timeout_enforced(self) -> None:
        args = {'tenant_id': 'tenant_alba_demo', 'decision_id': 'dec_demo_001', 'lang': 'ja'}
        with self.assertRaises(TimeoutError):
            invoke_mcp_tool(
                "approvals",
                "request_approval",
                args,
                bearer_token="dev-mcp-token",
                approval_id="apr_contract_001",
                user_confirmed=True,
                simulated_latency_ms=25_000.0,
            )


if __name__ == "__main__":
    unittest.main()
