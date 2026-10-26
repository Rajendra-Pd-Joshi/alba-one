"""Unit tests for Japanese and English PII redaction (`kb/pii.py`)."""

from __future__ import annotations

import importlib.util as _ilu
import pathlib as _pl
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.kb.pii import PIIRedactor  # noqa: E402


class TestPIIRedaction(unittest.TestCase):
    """Verify PII scrubbing across Japanese and English samples before embedding."""

    def test_japanese_pii_samples_redacted(self) -> None:
        redactor = PIIRedactor()
        jp_sample = (
            "担当者の渡辺 剛（マイナンバー: 1234-5678-9012、電話: 090-1234-5678、"
            "自宅〒140-0003、メール: watanabe@example.co.jp）がクレーン作業を実施。"
        )
        res = redactor.redact(jp_sample)
        self.assertTrue(res.contains_pii)
        self.assertNotIn("渡辺 剛", res.redacted_text)
        self.assertNotIn("1234-5678-9012", res.redacted_text)
        self.assertNotIn("090-1234-5678", res.redacted_text)
        self.assertNotIn("140-0003", res.redacted_text)
        self.assertNotIn("watanabe@example.co.jp", res.redacted_text)

        self.assertIn("[PII_PERSON]", res.redacted_text)
        self.assertIn("[PII_MYNUMBER]", res.redacted_text)
        self.assertIn("[PII_PHONE]", res.redacted_text)
        self.assertIn("[PII_POSTAL_JP]", res.redacted_text)
        self.assertIn("[PII_EMAIL]", res.redacted_text)

    def test_english_and_fullwidth_pii_samples_redacted(self) -> None:
        redactor = PIIRedactor(person_names=["Tsuyoshi Watanabe", "Jane Doe"])
        en_sample = (
            "Contact Tsuyoshi Watanabe or Jane Doe at +81-3-5555-0199, "
            "Postal Code: 100-0001, Personal ID 987654321012, or jane.doe@albaconnect.example."
        )
        res = redactor.redact(en_sample)
        self.assertNotIn("Tsuyoshi Watanabe", res.redacted_text)
        self.assertNotIn("Jane Doe", res.redacted_text)
        self.assertNotIn("+81-3-5555-0199", res.redacted_text)
        self.assertNotIn("100-0001", res.redacted_text)
        self.assertNotIn("987654321012", res.redacted_text)
        self.assertNotIn("jane.doe@albaconnect.example", res.redacted_text)
        self.assertGreaterEqual(res.total_redactions, 6)


if __name__ == "__main__":
    unittest.main()
