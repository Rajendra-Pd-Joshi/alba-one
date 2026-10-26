"""LangChain `ChatOpenAI` factory pointed at `GATEWAY_BASE_URL` (Principle 6).

Assumed target versions:
- `langchain-openai>=0.2.2`
- `langchain-core>=0.3.10`

Supports Portkey (default), Bifrost, TensorZero, and Mesh API purely via
environment variables (`GATEWAY_PROVIDER`, `GATEWAY_BASE_URL`, `GATEWAY_API_KEY`,
`GATEWAY_EXTRA_HEADERS_JSON`).
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from alba_one.core.config import Settings, get_settings
from alba_one.gateway.routing import (
    GatewayCallMetadata,
    build_gateway_headers,
    resolve_fallback_chain,
)


def create_chat_model(
    *,
    metadata: GatewayCallMetadata,
    model_role: str = "main",
    temperature: float = 0.0,
    with_fallbacks: bool = True,
    settings: Settings | None = None,
) -> BaseChatModel:
    """Create a configured `ChatOpenAI` instance routed through the LLM Gateway.

    Args:
        metadata: Per-call tenant_id, task, prompt_version, and optional trace_id.
        model_role: Which configured model slot to use ('main', 'judge', 'eval_judge').
        temperature: Sampling temperature (defaults to 0.0 for deterministic reasoning).
        with_fallbacks: If True and `FALLBACK_MODELS` is set, wraps primary `ChatOpenAI`
            with `.with_fallbacks(...)` in addition to gateway-level fallback headers.
        settings: Optional injected `Settings` instance for testing.

    Returns:
        A `ChatOpenAI` (or `RunnableWithFallbacks` wrapping `ChatOpenAI`) ready for
        structured output or tool calling.
    """
    cfg = settings or get_settings()

    if model_role == "main":
        primary_model = cfg.main_model
    elif model_role == "judge":
        primary_model = cfg.judge_model
    elif model_role == "eval_judge":
        primary_model = cfg.eval_judge_model
    else:
        raise ValueError(f"Unknown model_role '{model_role}'. Expected 'main', 'judge', or 'eval_judge'.")

    chain = resolve_fallback_chain(primary_model, cfg.fallback_model_list)
    fallbacks = chain[1:]

    headers = build_gateway_headers(
        provider=cfg.gateway_provider,
        gateway_api_key=cfg.gateway_api_key,
        metadata=metadata,
        extra_headers=cfg.gateway_extra_headers,
        fallback_models=fallbacks,
        primary_model=primary_model,
    )

    # When using Portkey pass-through or direct OpenAI-compatible gateways,
    # OPENAI_API_KEY is passed as the bearer token while x-portkey-api-key
    # authenticates with Portkey.
    api_key_value = (
        cfg.openai_api_key if cfg.gateway_provider.lower() == "portkey" else cfg.gateway_api_key
    )

    def _instantiate(model_name: str, call_headers: dict[str, str]) -> ChatOpenAI:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "base_url": cfg.gateway_base_url,
            "api_key": SecretStr(api_key_value),
            "temperature": temperature,
            "timeout": cfg.llm_timeout_seconds,
            "max_retries": cfg.llm_max_retries,
            "default_headers": call_headers,
        }
        return ChatOpenAI(**kwargs)

    primary_llm = _instantiate(primary_model, headers)

    if with_fallbacks and fallbacks:
        fallback_llms = [_instantiate(m, headers) for m in fallbacks]
        return primary_llm.with_fallbacks(fallback_llms)  # type: ignore[return-value]

    return primary_llm
