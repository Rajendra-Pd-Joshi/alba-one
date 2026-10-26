"""Pure gateway header and fallback-chain construction logic (stdlib only).

Allows Portkey (default), Bifrost, TensorZero, and Mesh API to be swapped via
environment variables (`GATEWAY_PROVIDER`, `GATEWAY_BASE_URL`, `GATEWAY_API_KEY`,
`GATEWAY_EXTRA_HEADERS_JSON`) without code changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SUPPORTED_GATEWAYS: frozenset[str] = frozenset({"portkey", "bifrost", "tensorzero", "mesh"})

METADATA_HEADER_BY_PROVIDER: dict[str, str] = {
    "portkey": "x-portkey-metadata",
    "bifrost": "x-bf-metadata",
    "tensorzero": "x-tensorzero-tags",
    "mesh": "x-mesh-metadata",
}


@dataclass(frozen=True)
class GatewayCallMetadata:
    """Per-call metadata attached to every LLM request for audit and tenant isolation."""

    tenant_id: str
    task: str
    prompt_version: str
    trace_id: str | None = None
    user_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Serialize metadata into string key-value pairs."""
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required on GatewayCallMetadata.")
        if not self.task.strip():
            raise ValueError("task is required on GatewayCallMetadata.")
        if not self.prompt_version.strip():
            raise ValueError("prompt_version is required on GatewayCallMetadata.")
        payload: dict[str, str] = {
            "tenant_id": self.tenant_id.strip(),
            "task": self.task.strip(),
            "prompt_version": self.prompt_version.strip(),
        }
        if self.trace_id:
            payload["trace_id"] = self.trace_id.strip()
        if self.user_id:
            payload["user_id"] = self.user_id.strip()
        return payload


def build_gateway_headers(
    *,
    provider: str,
    gateway_api_key: str,
    metadata: GatewayCallMetadata,
    extra_headers: dict[str, str] | None = None,
    fallback_models: list[str] | None = None,
    primary_model: str | None = None,
) -> dict[str, str]:
    """Construct HTTP headers for an OpenAI-compatible LLM gateway call.

    - Portkey uses `x-portkey-api-key`, `x-portkey-metadata`, and optional
      `x-portkey-config` (for gateway-side automatic fallback routing).
    - Bifrost, TensorZero, and Mesh API use standard `Authorization` (handled by
      the OpenAI SDK `api_key`) plus their provider-specific metadata headers
      and unified `x-alba-*` headers.
    """
    norm_provider = provider.strip().lower()
    if norm_provider not in SUPPORTED_GATEWAYS:
        raise ValueError(
            f"Unsupported GATEWAY_PROVIDER '{provider}'. Must be one of {sorted(SUPPORTED_GATEWAYS)}."
        )

    meta_dict = metadata.to_dict()
    meta_json = json.dumps(meta_dict, separators=(",", ":"), sort_keys=True)
    meta_header_name = METADATA_HEADER_BY_PROVIDER[norm_provider]

    headers: dict[str, str] = {
        meta_header_name: meta_json,
        "x-alba-tenant-id": meta_dict["tenant_id"],
        "x-alba-task": meta_dict["task"],
        "x-alba-prompt-version": meta_dict["prompt_version"],
    }
    if metadata.trace_id:
        headers["x-trace-id"] = metadata.trace_id

    if norm_provider == "portkey":
        headers["x-portkey-api-key"] = gateway_api_key
        if primary_model and fallback_models:
            portkey_routing: dict[str, Any] = {
                "strategy": {"mode": "fallback"},
                "targets": [
                    {"override_params": {"model": m}}
                    for m in [primary_model, *fallback_models]
                ],
            }
            headers["x-portkey-config"] = json.dumps(portkey_routing, separators=(",", ":"))
    else:
        headers["x-gateway-api-key"] = gateway_api_key

    if extra_headers:
        for k, v in extra_headers.items():
            headers[str(k)] = str(v)

    return headers


def resolve_fallback_chain(primary_model: str, fallback_models: list[str]) -> list[str]:
    """Return de-duplicated ordered list `[primary_model, *fallback_models]`."""
    primary = primary_model.strip()
    if not primary:
        raise ValueError("primary_model cannot be empty.")
    chain: list[str] = [primary]
    for candidate in fallback_models:
        cleaned = candidate.strip()
        if cleaned and cleaned not in chain:
            chain.append(cleaned)
    return chain
