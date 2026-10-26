"""Pure environment variable and model catalog validation logic (no third-party deps beyond PyYAML).

Used by both `core/config.py` (Pydantic v2 `BaseSettings`) and startup health checks
so that missing variables produce a readable bilingual error naming the exact variable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "MAIN_MODEL",
    "JUDGE_MODEL",
    "EVAL_JUDGE_MODEL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "RERANK_PROVIDER",
    "RERANK_MODEL",
    "GATEWAY_BASE_URL",
    "GATEWAY_API_KEY",
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "PINECONE_INDEX_NAME",
    "COHERE_API_KEY",
    "REDIS_URL",
    "DATABASE_URL",
    "AWS_REGION",
    "BEDROCK_GUARDRAIL_ID",
    "BEDROCK_GUARDRAIL_VERSION",
    "LANGSMITH_API_KEY",
    "MEM0_API_KEY",
)


class MissingConfigurationError(ValueError):
    """Raised when one or more required configuration variables are missing or blank."""

    def __init__(self, missing_vars: list[str]) -> None:
        self.missing_vars = missing_vars
        joined = ", ".join(missing_vars)
        message = (
            f"Missing required configuration variable(s): {joined} / "
            f"必須の環境変数が設定されていません: {joined}"
        )
        super().__init__(message)


def validate_required_env_map(env_map: dict[str, str | None]) -> list[str]:
    """Return a list of missing or empty required variable names from `env_map`."""
    missing: list[str] = []
    for var_name in REQUIRED_ENV_VARS:
        val = env_map.get(var_name)
        if val is None or not str(val).strip():
            missing.append(var_name)
    return missing


def require_valid_env_map(env_map: dict[str, str | None]) -> None:
    """Raise `MissingConfigurationError` naming every missing variable if any are unset."""
    missing = validate_required_env_map(env_map)
    if missing:
        raise MissingConfigurationError(missing)


def check_eval_judge_distinct(main_model: str, eval_judge_model: str) -> str | None:
    """Return a warning message if `EVAL_JUDGE_MODEL` equals `MAIN_MODEL`, else None."""
    if main_model.strip() == eval_judge_model.strip():
        return (
            f"WARNING: EVAL_JUDGE_MODEL ('{eval_judge_model}') must differ from "
            f"MAIN_MODEL ('{main_model}') to prevent self-preference bias."
        )
    return None


def load_model_catalog(yaml_path: str | Path) -> dict[str, Any]:
    """Load the model catalog and gateway definitions from `config/models.yaml`."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Model configuration YAML not found at: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "models" not in data:
        raise ValueError(f"Invalid model catalog structure in {path}: missing 'models' key.")
    return data


def parse_model_prices(
    prices_json: str | None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]]:
    """Merge model pricing from `config/models.yaml` and `MODEL_PRICES_JSON` env var."""
    merged: dict[str, dict[str, float]] = {}
    if catalog and isinstance(catalog.get("models"), dict):
        for model_name, spec in catalog["models"].items():
            if isinstance(spec, dict):
                merged[str(model_name)] = {
                    "input_per_1m": float(spec.get("input_per_1m_usd", 0.0)),
                    "output_per_1m": float(spec.get("output_per_1m_usd", 0.0)),
                }
    if prices_json and prices_json.strip():
        parsed = json.loads(prices_json)
        if not isinstance(parsed, dict):
            raise ValueError("MODEL_PRICES_JSON must decode to a JSON object.")
        for model_name, rates in parsed.items():
            if not isinstance(rates, dict):
                raise ValueError(f"Price entry for '{model_name}' must be an object.")
            merged[str(model_name)] = {
                "input_per_1m": float(rates.get("input_per_1m", 0.0)),
                "output_per_1m": float(rates.get("output_per_1m", 0.0)),
            }
    return merged
