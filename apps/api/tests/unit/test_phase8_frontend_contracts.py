"""Unit & contract tests for Phase 8 Frontend Brand Tokens, i18n Parity, OpenAPI Schema Sync & Mock Guard (`test_phase8_frontend_contracts.py`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.agents.decision_state import ALL_DECISION_STATES
from alba_one.kb.indexer import find_repo_root

ALLOWED_BRAND_HEX = frozenset(
    {
        "#0052FF",
        "#006685",
        "#8424DA",
        "#B6250A",
        "#1B1B1B",
        "#5E5E5E",
        "#C6C6C6",
        "#E2E2E2",
        "#FFFFFF",
        "#F7F7F7",
    }
)
EXPECTED_LOGO_SHA256 = "5e77186d156577cc589b350f9d1f17a0e58df92596268f14cf83267695223e52"


def _flatten_keys(obj: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in obj.items():
        full = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_keys(v, full))
        else:
            out.add(full)
    return out


class TestPhase8FrontendContracts(unittest.TestCase):
    """Verify ALBACONNECT brand tokens, logo hash, ja/en message parity, OpenAPI schema sync, and mock guard."""

    def setUp(self) -> None:
        self.root = find_repo_root()
        self.web_dir = self.root / "apps" / "web"

    def test_tailwind_brand_tokens_exact_hex_and_fonts_with_zero_non_brand_colors(self) -> None:
        tw_text = (self.web_dir / "tailwind.config.ts").read_text(encoding="utf-8")
        found_hex = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", tw_text)}
        self.assertEqual(found_hex, ALLOWED_BRAND_HEX)
        # Ensure forbidden previous non-brand hex codes and green never appear
        for forbidden in ("#1A365D", "#00A3C4", "#F7FAFC", "#00FF00", "#10B981", "#22C55E"):
            self.assertNotIn(forbidden, tw_text.upper())
        for font in ("Zen Kaku Gothic New", "Manrope", "Inter Tight"):
            self.assertIn(font, tw_text)

    def test_committed_albaconnect_logo_svg_hash_unmodified(self) -> None:
        logo_bytes = (self.web_dir / "public" / "brand" / "albaconnect-logo.svg").read_bytes()
        sha = hashlib.sha256(logo_bytes).hexdigest()
        self.assertEqual(sha, EXPECTED_LOGO_SHA256)

    def test_ja_and_en_messages_and_glossary_action_labels_parity(self) -> None:
        ja = json.loads((self.web_dir / "messages" / "ja.json").read_text(encoding="utf-8"))
        en = json.loads((self.web_dir / "messages" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(_flatten_keys(ja), _flatten_keys(en))

        # Check the 4 exact HITL action labels in ja.json, en.json, and i18n/glossary.json
        self.assertEqual(ja["action_bar"]["approve"], "承認")
        self.assertEqual(en["action_bar"]["approve"], "Approve")
        self.assertEqual(ja["action_bar"]["approve_with_conditions"], "条件付き承認")
        self.assertEqual(en["action_bar"]["approve_with_conditions"], "Approve with conditions")
        self.assertEqual(ja["action_bar"]["reject"], "却下")
        self.assertEqual(en["action_bar"]["reject"], "Reject")
        self.assertEqual(ja["action_bar"]["request_more_evidence"], "追加根拠を依頼")
        self.assertEqual(en["action_bar"]["request_more_evidence"], "Request more evidence")

    def test_openapi_schema_dts_and_mocks_match_backend_enums_and_states(self) -> None:
        schema_dts = (self.web_dir / "src" / "lib" / "api" / "schema.d.ts").read_text(encoding="utf-8")
        for verdict in ("recommend_approve", "recommend_approve_with_conditions", "recommend_reject", "needs_more_info"):
            self.assertIn(f'"{verdict}"', schema_dts)
        for action in ("approve", "approve_with_conditions", "reject", "request_more_evidence"):
            self.assertIn(f'"{action}"', schema_dts)
        for st in ALL_DECISION_STATES:
            self.assertIn(f'"{st}"', schema_dts)

        mocks_ts = (self.web_dir / "src" / "lib" / "api" / "mocks.ts").read_text(encoding="utf-8")
        for required_fixture in ("dec_mock_gates_ja", "dec_mock_no_hypotheses", "dec_mock_guardrail_blocked", "out_mock_01"):
            self.assertIn(required_fixture, mocks_ts)

    def test_production_build_mock_guard_and_workspace_layout_order(self) -> None:
        next_cfg = (self.web_dir / "next.config.mjs").read_text(encoding="utf-8")
        self.assertIn("assertProductionBuildRejectsMocks", next_cfg)
        self.assertIn("NEXT_PUBLIC_USE_MOCKS", next_cfg)

        ws_tsx = (self.web_dir / "src" / "components" / "decision" / "DecisionWorkspace.tsx").read_text(encoding="utf-8")
        idx_summary = ws_tsx.index("ai-recommendation-heading")
        idx_gates = ws_tsx.index("gates-banner-heading")
        idx_table = ws_tsx.index("<ComparisonTable")
        idx_hyps = ws_tsx.index("<details")
        idx_action = ws_tsx.index("<StickyActionBar")
        self.assertTrue(idx_summary < idx_gates < idx_table < idx_hyps < idx_action)


if __name__ == "__main__":
    unittest.main()
