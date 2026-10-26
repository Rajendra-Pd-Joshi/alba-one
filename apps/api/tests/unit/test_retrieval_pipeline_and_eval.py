"""Unit tests for the end-to-end Phase 3 Retrieval Pipeline & `evals/retriever_eval.py`."""

from __future__ import annotations

import importlib.util as _ilu
import json
import pathlib as _pl
import tempfile
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.kb.indexer import build_default_demo_kb  # noqa: E402
from alba_one.retrieval.pipeline import RetrievalPipeline  # noqa: E402

REPO_ROOT = _pl.Path(__file__).resolve().parents[4]


class TestRetrievalPipelineAndEval(unittest.TestCase):
    """Verify end-to-end retrieval pipeline execution, 60-item golden dataset, and ablation eval."""

    def test_end_to_end_pipeline_ja_and_en_queries(self) -> None:
        indexer, _, _ = build_default_demo_kb(repo_root=REPO_ROOT)
        pipeline = RetrievalPipeline(indexer=indexer)

        out_ja = pipeline.run(
            "東京大井ふ頭から横浜本牧への配送ルートRT-KNT-101の割当車両とSLA時間は？",
            lang="ja",
        )
        self.assertEqual(out_ja.status, "grounded_kb")
        self.assertGreaterEqual(len(out_ja.final_chunks), 1)
        self.assertIn("VH-REEFER-08", out_ja.final_chunks[0]["text"])
        self.assertGreaterEqual(len(out_ja.telemetry), 5)

        out_en = pipeline.run(
            "What are the nDCG@10 and p95 latency metrics for candidate model v2.4.0-rc1?",
            lang="en",
        )
        self.assertEqual(out_en.status, "grounded_kb")
        self.assertGreaterEqual(len(out_en.final_chunks), 1)
        self.assertTrue(
            any("0.881" in c.get("expanded_text", c["text"]) for c in out_en.final_chunks)
        )

    def test_retriever_goldens_has_60_items_half_ja_half_en_and_eval_runs(self) -> None:
        goldens_path = REPO_ROOT / "goldens" / "retriever.json"
        items = json.loads(goldens_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(items), 60)

        ja_items = [x for x in items if x["lang"] == "ja"]
        en_items = [x for x in items if x["lang"] == "en"]
        self.assertEqual(len(ja_items), 30)
        self.assertEqual(len(en_items), 30)
        self.assertTrue(all(x["status"] == "draft" for x in items))

        eval_path = REPO_ROOT / "evals" / "retriever_eval.py"
        spec = _ilu.spec_from_file_location("retriever_eval", eval_path)
        assert spec and spec.loader
        eval_mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(eval_mod)

        # Refuses to run without --allow-draft
        with self.assertRaises(RuntimeError):
            eval_mod.run_retriever_eval(goldens_path, allow_draft=False, smoke_limit=4)

        # Runs 5-way ablation on smoke subset with --allow-draft
        with tempfile.TemporaryDirectory() as tmpdir:
            report = eval_mod.run_retriever_eval(
                goldens_path,
                allow_draft=True,
                compare=True,
                smoke_limit=10,
                out_dir=tmpdir,
            )
            self.assertEqual(len(report["results"]), 5)
            configs = [r["configuration"] for r in report["results"]]
            self.assertEqual(
                configs,
                [
                    "dense_only",
                    "keyword_only",
                    "hybrid",
                    "hybrid_rerank",
                    "hybrid_rerank_corrective",
                ],
            )
            full_cfg = report["results"][-1]["overall"]
            self.assertGreaterEqual(full_cfg["recall_at_5"], 0.8)


if __name__ == "__main__":
    unittest.main()
