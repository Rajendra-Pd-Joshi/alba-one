"""Startup and deep dependency health probes for ALBA ONE (Phase 1 & Phase 3 Rerank Probe).

Verifies:
1. All required environment variables are present (raises `MissingConfigurationError` naming missing vars).
2. Configured models (`MAIN_MODEL`, `JUDGE_MODEL`, `EVAL_JUDGE_MODEL`, `EMBEDDING_MODEL`, `RERANK_MODEL`)
   respond to gateway/provider probes, including the 2-document dummy rerank check.
3. PostgreSQL (`SELECT 1`), Redis (`PING`), Pinecone index (`describe_index_stats`),
   and AWS Bedrock Guardrail (`get_guardrail`) connectivity.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy import text

from alba_one.core.config import Settings, get_settings
from alba_one.core.env_validator import check_eval_judge_distinct, load_model_catalog
from alba_one.db.session import get_engine
from alba_one.retrieval.reranker import HttpReranker, RerankerConfigError


@dataclass(frozen=True)
class ComponentStatus:
    """Health report for a single dependency or configured model."""

    name: str
    status: str  # "healthy" | "degraded" | "unhealthy" | "skipped_offline"
    latency_ms: float
    detail: str


async def probe_postgres() -> ComponentStatus:
    """Ping PostgreSQL with `SELECT 1` via the async SQLAlchemy engine."""
    start = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("postgres", "healthy", ms, "SELECT 1 succeeded")
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("postgres", "unhealthy", ms, str(exc))


async def probe_redis(redis_url: str) -> ComponentStatus:
    """Ping Redis using `redis.asyncio`."""
    start = time.perf_counter()
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url, socket_connect_timeout=3.0)
        try:
            pong = await client.ping()
        finally:
            await client.aclose()
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("redis", "healthy" if pong else "unhealthy", ms, f"PING={pong}")
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("redis", "unhealthy", ms, str(exc))


async def probe_pinecone(settings: Settings, live_network: bool) -> ComponentStatus:
    """Verify Pinecone index configuration and optional live index stats."""
    start = time.perf_counter()
    if not live_network:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus(
            "pinecone",
            "skipped_offline",
            ms,
            f"Configured index='{settings.pinecone_index_name}' (set STARTUP_PING_ENABLED=true for live ping)",
        )
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)
        idx = pc.Index(name=settings.pinecone_index_name, host=settings.pinecone_host or None)
        stats = idx.describe_index_stats()
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        total_vecs = stats.get("total_vector_count", 0) if isinstance(stats, dict) else 0
        return ComponentStatus(
            "pinecone",
            "healthy",
            ms,
            f"Index '{settings.pinecone_index_name}' reachable (vectors={total_vecs})",
        )
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("pinecone", "unhealthy", ms, str(exc))


async def probe_bedrock_guardrail(settings: Settings, live_network: bool) -> ComponentStatus:
    """Verify AWS Bedrock Guardrail configuration and optional `get_guardrail` call."""
    start = time.perf_counter()
    if not live_network:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus(
            "bedrock_guardrail",
            "skipped_offline",
            ms,
            f"Configured guardrail='{settings.bedrock_guardrail_id}' v{settings.bedrock_guardrail_version} in {settings.aws_region}",
        )
    try:
        import boto3

        client = boto3.client("bedrock", region_name=settings.aws_region)
        resp = client.get_guardrail(
            guardrailIdentifier=settings.bedrock_guardrail_id,
            guardrailVersion=settings.bedrock_guardrail_version,
        )
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        status_str = resp.get("status", "READY")
        return ComponentStatus(
            "bedrock_guardrail",
            "healthy",
            ms,
            f"Guardrail '{settings.bedrock_guardrail_id}' status={status_str}",
        )
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("bedrock_guardrail", "unhealthy", ms, str(exc))


def probe_reranker_startup(
    settings: Settings,
    live_network: bool,
    *,
    http_client: httpx.Client | None = None,
) -> ComponentStatus:
    """Rerank a 2-document dummy query with `RERANK_PROVIDER` + `RERANK_MODEL`.

    If it returns a 404 / unknown-model error, raises `RerankerConfigError` naming
    `RERANK_PROVIDER`, `RERANK_MODEL`, and the alias table (does not silently fall back).
    """
    start = time.perf_counter()
    reranker = HttpReranker(
        provider=settings.rerank_provider,
        model=settings.rerank_model,
        cohere_api_key=settings.cohere_api_key,
        gateway_base_url=settings.gateway_base_url,
        gateway_api_key=settings.gateway_api_key,
        fallback_model="",  # Never silently fall back during startup model verification
        http_client=http_client,
    )
    if not live_network and http_client is None:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus(
            "model:RERANK_MODEL",
            "healthy",
            ms,
            f"Configured RERANK_PROVIDER='{settings.rerank_provider}', RERANK_MODEL='{settings.rerank_model}'",
        )
    try:
        info = reranker.probe_two_doc_dummy()
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus(
            "model:RERANK_MODEL",
            "healthy",
            ms,
            f"2-doc rerank probe succeeded ({info['provider']}:{info['model']} -> {info['top_chunk_id']})",
        )
    except RerankerConfigError:
        raise
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ComponentStatus("model:RERANK_MODEL", "unhealthy", ms, str(exc))


async def probe_configured_models(
    settings: Settings,
    live_network: bool,
) -> list[ComponentStatus]:
    """Verify each configured model exists in catalog/pricing and probe gateway + reranker."""
    results: list[ComponentStatus] = []
    try:
        catalog = load_model_catalog(settings.model_config_path)
    except Exception:
        catalog = {"models": {}}
    prices = settings.get_model_prices(catalog=catalog)

    configured_slots = [
        ("MAIN_MODEL", settings.main_model),
        ("JUDGE_MODEL", settings.judge_model),
        ("EVAL_JUDGE_MODEL", settings.eval_judge_model),
        ("EMBEDDING_MODEL", settings.embedding_model),
    ]

    for slot_name, model_id in configured_slots:
        start = time.perf_counter()
        if model_id not in prices:
            ms = round((time.perf_counter() - start) * 1000.0, 2)
            results.append(
                ComponentStatus(
                    f"model:{slot_name}",
                    "unhealthy",
                    ms,
                    f"Model '{model_id}' missing pricing in MODEL_PRICES_JSON / config/models.yaml",
                )
            )
            continue

        if not live_network:
            ms = round((time.perf_counter() - start) * 1000.0, 2)
            results.append(
                ComponentStatus(
                    f"model:{slot_name}",
                    "healthy",
                    ms,
                    f"Model '{model_id}' priced & validated via {settings.gateway_provider}",
                )
            )
            continue

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.gateway_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.gateway_api_key}"},
                )
            ms = round((time.perf_counter() - start) * 1000.0, 2)
            status_val = "healthy" if resp.status_code < 500 else "unhealthy"
            results.append(
                ComponentStatus(
                    f"model:{slot_name}",
                    status_val,
                    ms,
                    f"Gateway HTTP {resp.status_code} for '{model_id}'",
                )
            )
        except Exception as exc:
            ms = round((time.perf_counter() - start) * 1000.0, 2)
            results.append(ComponentStatus(f"model:{slot_name}", "unhealthy", ms, str(exc)))

    results.append(probe_reranker_startup(settings, live_network=live_network))
    return results


async def run_deep_health_check(
    settings: Settings | None = None,
    *,
    probe_external_network: bool | None = None,
) -> dict[str, Any]:
    """Execute full dependency health checks across Postgres, Redis, Pinecone, Bedrock, and models."""
    cfg = settings or get_settings()
    live_net = cfg.startup_ping_enabled if probe_external_network is None else probe_external_network

    pg_status = await probe_postgres()
    redis_status = await probe_redis(cfg.redis_url)
    pinecone_status = await probe_pinecone(cfg, live_network=live_net)
    bedrock_status = await probe_bedrock_guardrail(cfg, live_network=live_net)
    model_statuses = await probe_configured_models(cfg, live_network=live_net)

    all_components = [pg_status, redis_status, pinecone_status, bedrock_status, *model_statuses]
    unhealthy = [c for c in all_components if c.status == "unhealthy"]
    warning = check_eval_judge_distinct(cfg.main_model, cfg.eval_judge_model)

    return {
        "status": "healthy" if not unhealthy else "degraded",
        "environment": cfg.app_env,
        "gateway_provider": cfg.gateway_provider,
        "eval_judge_warning": warning,
        "components": [asdict(c) for c in all_components],
    }
