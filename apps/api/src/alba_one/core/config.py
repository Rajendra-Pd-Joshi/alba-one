"""Application settings powered by `pydantic-settings` (Principle 2 & Principle 6)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from alba_one.core.env_validator import (
    MissingConfigurationError,
    check_eval_judge_distinct,
    parse_model_prices,
    require_valid_env_map,
)


class Settings(BaseSettings):
    """Centralized, strictly typed configuration for ALBA ONE."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 1. Runtime & App
    app_env: str = Field(default="development")
    default_language: str = Field(default="ja")
    log_level: str = Field(default="INFO")
    model_config_path: str = Field(default="config/models.yaml")
    startup_ping_enabled: bool = Field(default=False)
    openapi_docs_enabled: bool = Field(default=False)
    cors_allowed_origins: str = Field(default="http://localhost:3000")
    cors_allow_credentials: bool = Field(default=True)
    trace_capture_content: bool = Field(default=False)

    # 2. Models & Pricing (`RERANK_MODEL` is a free string, never validated against a fixed list)
    main_model: str = Field(..., min_length=1)
    judge_model: str = Field(..., min_length=1)
    eval_judge_model: str = Field(..., min_length=1)
    fallback_models: str = Field(default="")
    embedding_model: str = Field(..., min_length=1)
    embedding_dimensions: int = Field(..., ge=64, le=4096)
    rerank_provider: str = Field(default="cohere_direct", min_length=1)
    rerank_model: str = Field(default="rerank-v4.0-pro", min_length=1)
    rerank_fallback_model: str = Field(default="")
    rerank_top_k: int = Field(default=5, ge=1, le=50)
    model_prices_json: str = Field(default="{}")

    # 3. Retrieval Pipeline Settings (Phase 3)
    default_chunking_strategy: str = Field(default="parent_child")
    query_rewrite_count: int = Field(default=4, ge=1, le=10)
    relevance_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    allow_external_fallback: bool = Field(default=True)
    enable_multimodal_rag: bool = Field(default=False)

    # 4. LLM Gateway
    gateway_provider: str = Field(default="portkey")
    gateway_base_url: str = Field(..., min_length=1)
    gateway_api_key: str = Field(..., min_length=1)
    gateway_extra_headers_json: str = Field(default="{}")
    llm_timeout_seconds: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)

    # 5. Upstream Model & Vector Providers
    openai_api_key: str = Field(..., min_length=1)
    pinecone_api_key: str = Field(..., min_length=1)
    pinecone_index_name: str = Field(..., min_length=1)
    pinecone_host: str = Field(default="")
    cohere_api_key: str = Field(..., min_length=1)

    # 6. Stores, Cache & Rate Limiting
    database_url: str = Field(..., min_length=1)
    redis_url: str = Field(..., min_length=1)
    llm_cache_ttl_seconds: int = Field(default=86400, ge=1)
    rate_limit_tenant_rpm: int = Field(default=300, ge=1)
    rate_limit_tenant_burst: int = Field(default=60, ge=1)
    rate_limit_user_rpm: int = Field(default=60, ge=1)
    rate_limit_user_burst: int = Field(default=15, ge=1)
    rate_limit_tool_rpm: int = Field(default=120, ge=1)
    rate_limit_tool_burst: int = Field(default=30, ge=1)

    # 7. Guardrails, Memory & Operational Controls (Phase 4)
    aws_region: str = Field(..., min_length=1)
    bedrock_guardrail_id: str = Field(..., min_length=1)
    bedrock_guardrail_version: str = Field(..., min_length=1)
    bedrock_guardrail_tier: str = Field(default="STANDARD")
    bedrock_guardrail_cross_region_profile: str = Field(default="apac.guardrail.v1:0")
    guardrail_mode: str = Field(default="enforce")
    allow_guardrail_monitor_in_prod: bool = Field(default=False)
    fetch_domain_policy: str = Field(default="denylist")
    outbound_query_policy: str = Field(default="block")

    memory_provider: str = Field(default="mem0")
    mem0_api_key: str = Field(..., min_length=1)
    mem0_org_id: str = Field(default="alba-connect")
    memory_default_ttl_seconds: int = Field(default=7776000, ge=1)

    ops_max_tokens_per_request: int = Field(default=32000, ge=100)
    ops_max_cost_usd_per_request: float = Field(default=1.50, gt=0.0)
    ops_max_cost_usd_per_tenant_daily: float = Field(default=250.0, gt=0.0)
    ops_max_graph_steps: int = Field(default=15, ge=1)
    ops_max_tool_calls_per_run: int = Field(default=10, ge=1)
    ops_kill_switch: bool = Field(default=False)

    # 8. Hypothesis Generator & Tool-Gathering Budgets (Phase 6 — TODO(owner): tune from measured ops evals)
    max_options: int = Field(default=4, ge=2, le=8)
    max_tool_calls_per_run: int = Field(default=10, ge=1, le=50)
    round1_max_calls: int = Field(default=6, ge=1, le=30)
    round2_max_calls: int = Field(default=4, ge=1, le=20)
    tool_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    max_run_cost: float = Field(default=0.50, gt=0.0)

    langsmith_tracing: bool = Field(default=True)
    langsmith_api_key: str = Field(..., min_length=1)
    langsmith_project: str = Field(default="alba-one-dev")

    # 9. OIDC / JWKS Authentication & S2S Dual-Secret Rotation (Phase 10)
    auth_stub_enabled: bool = Field(default=False)
    default_tenant_id: str = Field(default="tenant_alba_demo")
    default_user_id: str = Field(default="user_analyst_01")
    default_user_role: str = Field(default="analyst")
    oidc_issuer: str = Field(default="")
    oidc_audience: str = Field(default="")
    oidc_jwks_url: str = Field(default="")
    oidc_allowed_algorithms: str = Field(default="RS256,ES256")
    oidc_leeway_seconds: int = Field(default=30, ge=0, le=300)
    oidc_max_token_age_seconds: int = Field(default=3600, ge=60, le=86400)
    oidc_claim_tenant: str = Field(default="tenant_id")
    oidc_claim_roles: str = Field(default="roles")
    oidc_claim_lang: str = Field(default="lang")
    oidc_step_up_claim: str = Field(default="amr")
    oidc_step_up_values: str = Field(default="mfa,hwk,otp,webauthn")
    oidc_require_step_up_for_approvals: bool = Field(default=False)
    jwks_ttl_seconds: int = Field(default=300, ge=30)
    jwks_max_stale_seconds: int = Field(default=3600, ge=60)
    jwks_min_refresh_interval_seconds: int = Field(default=30, ge=5)
    internal_s2s_current_secret: str = Field(default="")
    internal_s2s_previous_secret: str = Field(default="")
    internal_s2s_previous_secret_expires_at: float = Field(default=0.0)

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ("ja", "en"):
            raise ValueError("DEFAULT_LANGUAGE must be 'ja' or 'en'.")
        return v

    @field_validator("rerank_provider")
    @classmethod
    def validate_rerank_provider(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("cohere_direct", "gateway"):
            raise ValueError("RERANK_PROVIDER must be 'cohere_direct' or 'gateway'.")
        return cleaned

    @field_validator("guardrail_mode")
    @classmethod
    def validate_guardrail_mode(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("enforce", "monitor"):
            raise ValueError("GUARDRAIL_MODE must be 'enforce' or 'monitor'.")
        return cleaned

    @field_validator("memory_provider")
    @classmethod
    def validate_memory_provider(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("mem0", "langmem", "in_memory"):
            raise ValueError("MEMORY_PROVIDER must be 'mem0', 'langmem', or 'in_memory'.")
        return cleaned

    @property
    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.fallback_models.split(",") if m.strip()]

    @property
    def gateway_extra_headers(self) -> dict[str, str]:
        raw = json.loads(self.gateway_extra_headers_json or "{}")
        return {str(k): str(v) for k, v in raw.items()}

    def get_model_prices(self, catalog: dict[str, Any] | None = None) -> dict[str, dict[str, float]]:
        return parse_model_prices(self.model_prices_json, catalog=catalog)

    def eval_judge_warning(self) -> str | None:
        return check_eval_judge_distinct(self.main_model, self.eval_judge_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings from environment/.env, raising a clear error naming any missing variable."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        missing_fields = [str(err["loc"][0]).upper() for err in exc.errors() if err.get("loc")]
        if missing_fields:
            raise MissingConfigurationError(missing_fields) from exc
        require_valid_env_map(dict(os.environ))
        raise
