"""Unit tests for Phase 2 Ontology (`kb/ontology_logic.py`) and Extractors (`kb/extractors.py`)."""

from __future__ import annotations

import importlib.util as _ilu
import pathlib as _pl
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.kb.extractors import (  # noqa: E402
    build_readonly_view_sql,
    extract_documents_from_seed_snapshot,
)
from alba_one.kb.ontology_logic import (  # noqa: E402
    REQUIRED_ENTITY_TYPES,
    load_ontology_catalog,
)

REPO_ROOT = _pl.Path(__file__).resolve().parents[4]


class TestOntologyAndExtractors(unittest.TestCase):
    """Verify ontology loading, ACL filtering, DBA read-only view guards, and bilingual extraction."""

    def test_load_demo_ontology_and_acl_filtering(self) -> None:
        ontology = load_ontology_catalog(
            REPO_ROOT / "config" / "ontology_demo.yaml",
            expected_tenant_id="tenant_alba_demo",
        )
        for req_type in REQUIRED_ENTITY_TYPES:
            self.assertIn(req_type, ontology.entities)

        # Viewer role cannot access 'staff' or 'model_release' entities
        viewer_entities = {
            e.entity_type for e in ontology.filter_entities_for_acl({"role:viewer"})
        }
        self.assertIn("vessel", viewer_entities)
        self.assertIn("route", viewer_entities)
        self.assertNotIn("staff", viewer_entities)
        self.assertNotIn("model_release", viewer_entities)

        # Analyst role can access all 7 entities
        analyst_entities = {
            e.entity_type for e in ontology.filter_entities_for_acl({"role:analyst"})
        }
        self.assertEqual(len(analyst_entities), 7)

    def test_readonly_view_sql_blocks_unapproved_tables(self) -> None:
        sql = build_readonly_view_sql("v_kb_vessels_berths", incremental_since="2026-10-01")
        self.assertIn("FROM v_kb_vessels_berths WHERE tenant_id = :tenant_id", sql)
        self.assertIn("AND updated_at > :incremental_since", sql)

        with self.assertRaises(PermissionError):
            build_readonly_view_sql("users; DROP TABLE decisions;")

    def test_extract_bilingual_documents_from_seed_snapshot(self) -> None:
        ontology = load_ontology_catalog(REPO_ROOT / "config" / "ontology_demo.yaml")
        docs = extract_documents_from_seed_snapshot(
            REPO_ROOT / "infra" / "seed" / "synthetic_demo_data.json",
            ontology,
        )
        self.assertGreaterEqual(len(docs), 20)
        langs = {d.lang for d in docs}
        self.assertEqual(langs, {"ja", "en"})
        for d in docs:
            self.assertEqual(d.tenant_id, "tenant_alba_demo")
            self.assertTrue(d.is_synthetic)
            self.assertTrue(d.source_table)
            self.assertTrue(d.source_pk)
            self.assertGreaterEqual(len(d.entity_ids), 1)
            self.assertGreaterEqual(len(d.acl_tags), 1)


if __name__ == "__main__":
    unittest.main()
