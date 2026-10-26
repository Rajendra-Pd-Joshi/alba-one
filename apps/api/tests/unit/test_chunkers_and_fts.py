"""Unit tests for the 4 KB chunking strategies (`kb/chunkers.py`), FTS (`kb/fts.py`), and `evals/chunking_compare.py`."""

from __future__ import annotations

import importlib.util as _ilu
import pathlib as _pl
import tempfile
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.kb.chunkers import (  # noqa: E402
    SUPPORTED_CHUNKING_STRATEGIES,
    chunk_document,
)
from alba_one.kb.extractors import KnowledgeDocumentRecord  # noqa: E402
from alba_one.kb.fts import build_tokenized_tsvector_string, score_fts_match  # noqa: E402

REPO_ROOT = _pl.Path(__file__).resolve().parents[4]


class TestChunkersAndFTS(unittest.TestCase):
    """Verify all 4 chunking strategies, Japanese sentence splitting, FTS scoring, and eval runner."""

    def setUp(self) -> None:
        self.sample_doc = KnowledgeDocumentRecord(
            doc_id="doc_test_01",
            tenant_id="tenant_alba_demo",
            entity_type="vessel",
            title="船舶・バース計画: アルバ・オーロラ号",
            text=(
                "アルバ・オーロラ号（容量4800 TEU）は東京港大井第3バース（TYO-OI-B3）へ着岸予定です。"
                "積載貨物は医薬品定温コンテナであり、2〜8℃の温度管理が必要です！"
                "強風警報発令時は瞬間風速15m/s超過でガントリークレーン作業を一時停止しますか？はい、停止します。"
            ),
            source_table="demo_vessels_berths",
            source_view="v_kb_vessels_berths",
            source_pk="vessel_alba_aurora",
            entity_ids=["vessel_alba_aurora", "TYO-OI-B3"],
            acl_tags=["role:viewer", "role:analyst"],
            valid_from="2026-10-24T00:00:00+09:00",
            valid_to=None,
            updated_at="2026-10-24T09:00:00+09:00",
            lang="ja",
            structured_metadata={"berth_code": "TYO-OI-B3", "teu_capacity": 4800},
        )

    def test_all_four_chunking_strategies_produce_valid_chunks(self) -> None:
        for strategy in SUPPORTED_CHUNKING_STRATEGIES:
            chunks = chunk_document(self.sample_doc, self.sample_doc.text, strategy=strategy)
            self.assertGreaterEqual(len(chunks), 1, f"Strategy {strategy} produced 0 chunks")
            for chk in chunks:
                self.assertEqual(chk.tenant_id, "tenant_alba_demo")
                self.assertEqual(chk.strategy, strategy)
                self.assertIn("vessel_alba_aurora", chk.entity_ids)
                if strategy == "parent_child":
                    self.assertIsNotNone(chk.parent_chunk_id)
                    self.assertIn("parent_text", chk.metadata)

    def test_japanese_fts_tokenization_and_scoring(self) -> None:
        tok_str = build_tokenized_tsvector_string(self.sample_doc.text)
        self.assertIn("tyo-oi-b3", tok_str)
        score_hit = score_fts_match("東京港大井第3バース TYO-OI-B3 医薬品", tok_str)
        score_miss = score_fts_match("無関係なクエリ文字列", tok_str)
        self.assertGreater(score_hit, 0.3)
        self.assertGreater(score_hit, score_miss)

    def test_chunking_compare_eval_refuses_drafts_without_flag_and_runs_with_flag(self) -> None:
        eval_path = REPO_ROOT / "evals" / "chunking_compare.py"
        spec = _ilu.spec_from_file_location("chunking_compare", eval_path)
        assert spec and spec.loader
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)

        dataset = REPO_ROOT / "goldens" / "chunking_smoke.json"
        with self.assertRaises(RuntimeError):
            mod.run_chunking_comparison(dataset, allow_draft=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            report = mod.run_chunking_comparison(dataset, allow_draft=True, out_dir=tmpdir)
            self.assertEqual(len(report["strategies"]), 4)
            for strat_report in report["strategies"]:
                self.assertGreaterEqual(strat_report["recall_at_3"], 0.8)


if __name__ == "__main__":
    unittest.main()
