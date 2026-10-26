"""Unit tests verifying the synthetic demo company seed and Alembic migration coverage."""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl, sys as _sys
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestSeedAndMigrations(unittest.TestCase):
    """Verify Phase 1 Requirements 6 & 7: 12 core tables and synthetic demo company seed."""

    def test_alembic_migration_creates_all_12_required_tables(self) -> None:
        migration_path = (
            REPO_ROOT
            / "apps"
            / "api"
            / "alembic"
            / "versions"
            / "0001_initial_foundation.py"
        )
        source = migration_path.read_text(encoding="utf-8")
        required_tables = [
            "tenants",
            "users",
            "decisions",
            "hypotheses",
            "tool_calls",
            "approvals",
            "outcomes",
            "guardrail_events",
            "llm_calls",
            "kb_chunks",
            "kb_documents",
            "eval_runs",
        ]
        for table in required_tables:
            self.assertIn(f'"{table}"', source, f"Missing table '{table}' in Alembic migration")

    def test_synthetic_demo_seed_marks_every_row_is_synthetic_true(self) -> None:
        json_seed_path = REPO_ROOT / "infra" / "seed" / "synthetic_demo_data.json"
        data = json.loads(json_seed_path.read_text(encoding="utf-8"))

        self.assertTrue(data["tenant"]["is_synthetic"])
        self.assertEqual(data["tenant"]["id"], "tenant_alba_demo")

        required_collections = [
            "delivery_routes",
            "vessels_berths",
            "staff_shifts",
            "ml_model_releases",
            "decisions_with_outcomes",
        ]
        for key in required_collections:
            rows = data.get(key, [])
            self.assertGreaterEqual(len(rows), 2, f"Expected >=2 rows in seed collection '{key}'")
            for row in rows:
                self.assertTrue(
                    row.get("is_synthetic"),
                    f"Row {row.get('id')} in {key} is missing is_synthetic=True",
                )
                self.assertEqual(
                    row.get("tenant_id"),
                    "tenant_alba_demo",
                    f"Row {row.get('id')} in {key} has wrong tenant_id",
                )

        sql_seed_path = REPO_ROOT / "infra" / "seed" / "01_synthetic_demo_company.sql"
        sql_text = sql_seed_path.read_text(encoding="utf-8")
        self.assertNotIn("FALSE, -- is_synthetic", sql_text)
        self.assertIn("demo_delivery_routes", sql_text)
        self.assertIn("demo_vessels_berths", sql_text)
        self.assertIn("demo_staff_shifts", sql_text)
        self.assertIn("demo_ml_model_releases", sql_text)


if __name__ == "__main__":
    unittest.main()
