"""Shared FastMCP base runner, registry loader, bearer auth, rate limiting, and `tool_calls` audit logger (`mcp_servers/base.py`)."""

from __future__ import annotations

import argparse
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from alba_one.guardrails.types import GuardrailContext
from alba_one.guardrails import tool_layer
from alba_one.kb.indexer import find_repo_root


@dataclass(frozen=True)
class MCPServerRegistryEntry:
    """Single server specification loaded from `mcp_servers/registry.yaml`."""

    name: str
    server_class: str  # "read" | "write" | "external"
    profile: str  # "core" | "domain" | "external"
    transport: str
    port: int
    required_env: list[str]
    image_extra: str
    owner: str
    data_sensitivity: str
    purpose_ja: str
    purpose_en: str


@dataclass(frozen=True)
class ToolCallAuditEntry:
    """Audit log entry matching the `tool_calls` PostgreSQL table."""

    tool_call_id: str
    tenant_id: str
    mcp_server: str
    tool_name: str
    tool_class: str
    arguments: dict[str, Any]
    result_summary: str
    side_effecting: bool
    requires_approval: bool
    latency_ms: float
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MCPAuthError(PermissionError):
    """Raised when an MCP request is missing or fails bearer token verification."""


class MCPToolExecutionError(RuntimeError):
    """Structured bilingual error raised when an MCP tool fails validation or timeout."""

    def __init__(self, code: str, message_ja: str, message_en: str) -> None:
        self.code = code
        self.message_ja = message_ja
        self.message_en = message_en
        super().__init__(f"[{code}] {message_ja} / {message_en}")


def load_mcp_registry(registry_path: str | Path | None = None) -> dict[str, MCPServerRegistryEntry]:
    """Load and parse `apps/api/src/alba_one/mcp_servers/registry.yaml`."""
    if registry_path is None:
        root = find_repo_root()
        path = root / "apps" / "api" / "src" / "alba_one" / "mcp_servers" / "registry.yaml"
    else:
        path = Path(registry_path)

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    servers = raw.get("servers", {})
    out: dict[str, MCPServerRegistryEntry] = {}
    for name, spec in servers.items():
        out[str(name)] = MCPServerRegistryEntry(
            name=str(spec["name"]),
            server_class=str(spec["class"]),
            profile=str(spec["profile"]),
            transport=str(spec.get("transport", "streamable-http")),
            port=int(spec["port"]),
            required_env=[str(e) for e in spec.get("required_env", [])],
            image_extra=str(spec["image_extra"]),
            owner=str(spec["owner"]),
            data_sensitivity=str(spec["data_sensitivity"]),
            purpose_ja=str(spec.get("purpose_ja", "")),
            purpose_en=str(spec.get("purpose_en", "")),
        )
    return out


class MCPServerAuditRuntime:
    """Wraps MCP tool execution with bearer auth, Layer 5 tool guardrail, timeout, and `tool_calls` logging."""

    def __init__(
        self,
        server_name: str,
        *,
        expected_bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.server_name = server_name
        self.expected_token = expected_bearer_token or os.getenv("MCP_BEARER_TOKEN", "dev-mcp-token")
        self.timeout_seconds = timeout_seconds
        self.audit_log: list[ToolCallAuditEntry] = []

    def verify_bearer(self, auth_header_or_token: str | None) -> None:
        """Verify bearer token from caller against `MCP_BEARER_TOKEN`."""
        if not auth_header_or_token:
            raise MCPAuthError("Missing MCP bearer token.")
        cleaned = auth_header_or_token.strip()
        if cleaned.lower().startswith("bearer "):
            cleaned = cleaned[7:].strip()
        if cleaned != self.expected_token:
            raise MCPAuthError("Invalid MCP bearer token.")

    def invoke_guarded(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        bearer_token: str | None = "dev-mcp-token",
        approval_id: str | None = None,
        user_confirmed: bool = False,
        outbound_query_policy: str = "generalize",
        simulated_latency_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Verify auth, run Layer 5 tool guardrail (input + output), enforce timeout, and log to `tool_calls`."""
        self.verify_bearer(bearer_token)
        tenant_id = str(arguments.get("tenant_id", "tenant_alba_demo"))
        ctx = GuardrailContext(tenant_id=tenant_id, lang=str(arguments.get("lang", "ja")))

        pre_res = tool_layer.check(
            {
                "mcp_server": self.server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "approval_id": approval_id,
                "user_confirmed": user_confirmed,
                "outbound_query_policy": outbound_query_policy,
            },
            ctx,
        )
        if pre_res.action == "block":
            raise MCPToolExecutionError(
                code=pre_res.policy.upper(),
                message_ja=f"ツールガードレール（{pre_res.policy}）により実行が拒否されました。",
                message_en=f"Blocked by tool guardrail policy ({pre_res.policy}).",
            )

        sanitized_args = (
            dict(pre_res.sanitized_payload)
            if isinstance(pre_res.sanitized_payload, dict)
            else dict(arguments)
        )
        if approval_id and "approval_id" not in sanitized_args:
            sanitized_args["approval_id"] = approval_id
        if user_confirmed and "user_confirmed" not in sanitized_args:
            sanitized_args["user_confirmed"] = True

        start = time.perf_counter()
        if simulated_latency_ms > self.timeout_seconds * 1000.0:
            raise TimeoutError(
                f"MCP tool '{self.server_name}.{tool_name}' exceeded timeout ({self.timeout_seconds}s)."
            )
        raw_result = handler(sanitized_args)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0 + simulated_latency_ms, 2)

        spec = tool_layer.TOOL_CATALOG.get((self.server_name, tool_name), {"class": "read"})
        t_class = str(spec["class"])

        entry = ToolCallAuditEntry(
            tool_call_id=f"tc_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            mcp_server=self.server_name,
            tool_name=tool_name,
            tool_class=t_class,
            arguments=sanitized_args,
            result_summary=str(raw_result)[:240],
            side_effecting=(t_class == "write"),
            requires_approval=(t_class == "write"),
            latency_ms=elapsed_ms,
        )
        self.audit_log.append(entry)
        return {
            "tool_call_id": entry.tool_call_id,
            "mcp_server": self.server_name,
            "tool_name": tool_name,
            "tool_class": t_class,
            "external": t_class == "external",
            "latency_ms": elapsed_ms,
            "data": raw_result,
            "audit": asdict(entry),
        }


def run_mcp_server_cli(mcp_app: Any, default_port: int = 8100) -> int:
    """Parse `--transport stdio|streamable-http` and `--port` and start the FastMCP server."""
    parser = argparse.ArgumentParser(description="ALBA ONE FastMCP Server Entrypoint")
    parser.add_argument(
        "--transport",
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        choices=["stdio", "streamable-http", "sse"],
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", str(default_port))))
    parser.add_argument("--check-only", action="store_true", help="Validate server startup and exit")
    args = parser.parse_args()
    if args.check_only:
        return 0
    mcp_app.run(transport=args.transport)
    return 0
