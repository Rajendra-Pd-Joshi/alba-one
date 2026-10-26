"""Unit tests for bilingual glossary consistency, message catalog key parity, and locale helpers."""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl, sys as _sys
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alba_one.core.i18n import (
    check_message_catalog_parity,
    format_jpy,
    format_tokyo_timestamp,
    verify_glossary_file,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestI18nAndGlossary(unittest.TestCase):
    """Verify Principle 7: Japanese/English key parity and verbatim glossary terms."""

    def test_glossary_contains_all_canonical_terms_and_pillars(self) -> None:
        glossary_path = REPO_ROOT / "i18n" / "glossary.json"
        errors = verify_glossary_file(glossary_path)
        self.assertEqual(errors, [], f"Glossary verification failed: {errors}")

    def test_ja_and_en_message_catalogs_have_exact_key_parity(self) -> None:
        ja_path = REPO_ROOT / "apps" / "web" / "messages" / "ja.json"
        en_path = REPO_ROOT / "apps" / "web" / "messages" / "en.json"
        ja_data = json.loads(ja_path.read_text(encoding="utf-8"))
        en_data = json.loads(en_path.read_text(encoding="utf-8"))

        missing_in_en, missing_in_ja = check_message_catalog_parity(ja_data, en_data)
        self.assertEqual(missing_in_en, [], f"Keys missing in en.json: {missing_in_en}")
        self.assertEqual(missing_in_ja, [], f"Keys missing in ja.json: {missing_in_ja}")

    def test_jpy_and_tokyo_timestamp_formatting(self) -> None:
        self.assertEqual(format_jpy(125000, "ja"), "¥125,000")
        self.assertEqual(format_jpy(125000, "en"), "JPY 125,000")

        utc_dt = datetime(2026, 10, 24, 3, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(format_tokyo_timestamp(utc_dt, "ja"), "2026年10月24日 12:30 JST")
        self.assertEqual(format_tokyo_timestamp(utc_dt, "en"), "2026-10-24 12:30 JST")


if __name__ == "__main__":
    unittest.main()
