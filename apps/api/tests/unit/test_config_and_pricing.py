"""Unit tests for environment validation, model catalog loading, and token cost calculation."""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl, sys as _sys
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import unittest
from pathlib import Path

from alba_one.core.env_validator import (
    REQUIRED_ENV_VARS,
    MissingConfigurationError,
    check_eval_judge_distinct,
    load_model_catalog,
    parse_model_prices,
    require_valid_env_map,
)
from alba_one.core.pricing import calculate_llm_cost_usd

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestConfigAndPricing(unittest.TestCase):
    """Verify Principle 6: config-driven models, missing-variable error messages, and pricing."""

    def test_missing_env_variable_names_exact_var_in_ja_and_en(self) -> None:
        complete_env = {var: "test_value" for var in REQUIRED_ENV_VARS}
        del complete_env["PINECONE_API_KEY"]
        del complete_env["BEDROCK_GUARDRAIL_ID"]

        with self.assertRaises(MissingConfigurationError) as ctx:
            require_valid_env_map(complete_env)

        msg = str(ctx.exception)
        self.assertIn("PINECONE_API_KEY", msg)
        self.assertIn("BEDROCK_GUARDRAIL_ID", msg)
        self.assertIn("必須の環境変数が設定されていません", msg)

    def test_eval_judge_must_differ_from_main_model(self) -> None:
        warn = check_eval_judge_distinct("gpt-4o-2024-08-06", "gpt-4o-2024-08-06")
        self.assertIsNotNone(warn)
        self.assertIn("EVAL_JUDGE_MODEL", warn or "")

        no_warn = check_eval_judge_distinct("gpt-4o-2024-08-06", "claude-3-5-sonnet-20241022")
        self.assertIsNone(no_warn)

    def test_load_model_catalog_and_calculate_cost(self) -> None:
        catalog = load_model_catalog(REPO_ROOT / "config" / "models.yaml")
        prices = parse_model_prices(None, catalog=catalog)

        self.assertIn("gpt-4o-2024-08-06", prices)
        self.assertIn("claude-3-5-sonnet-20241022", prices)

        # 10,000 prompt tokens @ $2.50/1M = $0.025; 2,000 completion tokens @ $10.00/1M = $0.020
        cost = calculate_llm_cost_usd(
            model="gpt-4o-2024-08-06",
            prompt_tokens=10_000,
            completion_tokens=2_000,
            prices_by_model=prices,
        )
        self.assertAlmostEqual(cost, 0.045, places=6)

    def test_unknown_model_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            calculate_llm_cost_usd("unconfigured-model-id", 100, 100, {})


if __name__ == "__main__":
    unittest.main()
