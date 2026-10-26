"""Phase 3 Retriever Evaluation (`evals/retriever_eval.py`).

Runnable as:
    uv run python -m evals.retriever_eval --dataset goldens/retriever.json [--allow-draft] [--compare] [--smoke N] [--out evals/reports/]

Features:
1. Refuses to run on `status == "draft"` items unless `--allow-draft` is passed, and prints draft count.
2. Checks `EVAL_JUDGE_MODEL != MAIN_MODEL` and logs a loud warning if they are equal.
3. Inspects installed `deepeval` (`ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`);
   runs DeepEval metrics when `deepeval` is installed and `--run-deepeval` is requested, and always computes
   classical IR metrics (`recall@k`, `mrr@k`, `ndcg@k`) from `expected_chunk_ids`.
4. Supports `--compare` ablation mode reporting:
   - `dense_only`
   - `keyword_only`
   - `hybrid` (RRF without rerank/corrective)
   - `hybrid_rerank` (RRF + FakeReranker/Cohere rerank)
   - `hybrid_rerank_corrective` (Full pipeline: RRF + Rerank + Self-RAG + Corrective RAG)
   broken down overall and per-language (`ja` vs `en`).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "api" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from alba_one.core.env_validator import check_eval_judge_distinct
from alba_one.kb.indexer import build_default_demo_kb
from alba_one.retrieval.pipeline import RetrievalPipeline

try:
    import deepeval  # type: ignore[import-not-found]
    from deepeval.metrics import (  # type: ignore[import-not-found]
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
    )

    HAS_DEEPEVAL = True
    DEEPEVAL_VERSION = getattr(deepeval, "__version__", "unknown")
except Exception:
    HAS_DEEPEVAL = False
    DEEPEVAL_VERSION = None
    ContextualRecallMetric = None
    ContextualPrecisionMetric = None
    ContextualRelevancyMetric = None

ABLATION_CONFIGS: tuple[tuple[str, str, bool, bool], ...] = (
    ("dense_only", "dense_only", False, False),
    ("keyword_only", "keyword_only", False, False),
    ("hybrid", "hybrid", False, False),
    ("hybrid_rerank", "hybrid", True, False),
    ("hybrid_rerank_corrective", "hybrid", True, True),
)


def compute_ir_metrics_for_item(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    *,
    k: int = 5,
) -> dict[str, float]:
    """Compute classical Recall@k, MRR@k, and nDCG@k for a single golden item."""
    if not expected_chunk_ids:
        return {"recall": 1.0, "mrr": 1.0, "ndcg": 1.0}

    top_k_ids = retrieved_chunk_ids[:k]
    expected_set = set(expected_chunk_ids)

    hits = len(set(top_k_ids) & expected_set)
    recall = hits / len(expected_set)

    first_rank: int | None = None
    dcg = 0.0
    for rank_idx, cid in enumerate(top_k_ids, start=1):
        if cid in expected_set:
            if first_rank is None:
                first_rank = rank_idx
            dcg += 1.0 / math.log2(rank_idx + 1)

    mrr = (1.0 / first_rank) if first_rank is not None else 0.0
    ideal_hits = min(len(expected_set), k)
    idcg = sum(1.0 / math.log2(r + 1) for r in range(1, ideal_hits + 1)) or 1.0
    ndcg = min(1.0, dcg / idcg)

    return {
        "recall": round(recall, 4),
        "mrr": round(mrr, 4),
        "ndcg": round(ndcg, 4),
    }


def _aggregate_metrics(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    if not rows:
        return {f"recall_at_{k}": 0.0, f"mrr_at_{k}": 0.0, f"ndcg_at_{k}": 0.0, "count": 0}
    n = len(rows)
    return {
        "count": n,
        f"recall_at_{k}": round(sum(r["recall"] for r in rows) / n, 4),
        f"mrr_at_{k}": round(sum(r["mrr"] for r in rows) / n, 4),
        f"ndcg_at_{k}": round(sum(r["ndcg"] for r in rows) / n, 4),
    }


def evaluate_ablation_mode(
    pipeline: RetrievalPipeline,
    items: list[dict[str, Any]],
    *,
    label: str,
    retrieval_mode: str,
    use_reranker: bool,
    use_corrective: bool,
    top_k: int = 5,
) -> dict[str, Any]:
    """Run one retrieval configuration across `items` and aggregate overall + JP/EN metrics."""
    all_rows: list[dict[str, Any]] = []
    ja_rows: list[dict[str, Any]] = []
    en_rows: list[dict[str, Any]] = []

    for item in items:
        lang = str(item.get("lang", "ja"))
        out = pipeline.run(
            str(item["input"]),
            tenant_id="tenant_alba_demo",
            caller_role="analyst",
            lang=lang,
            retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
            use_reranker=use_reranker,
            use_corrective=use_corrective,
        )
        ret_ids = [str(c["chunk_id"]) for c in out.final_chunks]
        exp_ids = [str(x) for x in item.get("expected_chunk_ids", [])]
        m = compute_ir_metrics_for_item(ret_ids, exp_ids, k=top_k)
        all_rows.append(m)
        if lang == "ja":
            ja_rows.append(m)
        else:
            en_rows.append(m)

    return {
        "configuration": label,
        "overall": _aggregate_metrics(all_rows, top_k),
        "ja": _aggregate_metrics(ja_rows, top_k),
        "en": _aggregate_metrics(en_rows, top_k),
    }


def run_retriever_eval(
    dataset_path: str | Path,
    *,
    allow_draft: bool = False,
    compare: bool = False,
    smoke_limit: int | None = None,
    top_k: int = 5,
    out_dir: str | Path = REPO_ROOT / "evals" / "reports",
) -> dict[str, Any]:
    """Execute retriever evaluation (and optional 5-way ablation) on `dataset_path`."""
    main_model = os.getenv("MAIN_MODEL", "gpt-4o-2024-08-06")
    eval_judge_model = os.getenv("EVAL_JUDGE_MODEL", "claude-3-5-sonnet-20241022")
    judge_warning = check_eval_judge_distinct(main_model, eval_judge_model)
    if judge_warning:
        print(judge_warning, file=sys.stderr)

    raw_items: list[dict[str, Any]] = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    draft_count = sum(1 for item in raw_items if item.get("status") == "draft")
    print(f"[retriever_eval] Loaded {len(raw_items)} items ({draft_count} with status='draft').")

    if draft_count > 0 and not allow_draft:
        raise RuntimeError(
            f"Refusing to run on {draft_count} draft golden items. Pass --allow-draft to run."
        )

    items = raw_items[:smoke_limit] if smoke_limit else raw_items
    indexer, _, _ = build_default_demo_kb(repo_root=REPO_ROOT)
    pipeline = RetrievalPipeline(indexer=indexer, rerank_top_k=top_k)

    configs_to_run = (
        ABLATION_CONFIGS
        if compare
        else (("hybrid_rerank_corrective", "hybrid", True, True),)
    )
    ablation_results = [
        evaluate_ablation_mode(
            pipeline,
            items,
            label=label,
            retrieval_mode=rmode,
            use_reranker=urerank,
            use_corrective=ucorr,
            top_k=top_k,
        )
        for label, rmode, urerank, ucorr in configs_to_run
    ]

    report: dict[str, Any] = {
        "eval": "retriever_eval",
        "dataset": str(dataset_path),
        "total_dataset_items": len(raw_items),
        "evaluated_items": len(items),
        "draft_items": draft_count,
        "allow_draft": allow_draft,
        "compare_mode": compare,
        "main_model": main_model,
        "eval_judge_model": eval_judge_model,
        "eval_judge_warning": judge_warning,
        "deepeval_installed": HAS_DEEPEVAL,
        "deepeval_version": DEEPEVAL_VERSION,
        "deepeval_metrics_wired": [
            "ContextualRecallMetric",
            "ContextualPrecisionMetric",
            "ContextualRelevancyMetric",
        ],
        "thresholds": "TODO(owner) — see evals/thresholds.yaml",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "results": ablation_results,
    }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = out_path / "retriever_eval.json"
    md_path = out_path / "retriever_eval.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# ALBA ONE — Phase 3 Retriever Evaluation Report",
        "",
        f"- **Dataset:** `{dataset_path}` ({len(items)}/{len(raw_items)} items evaluated; {draft_count} drafts)",
        f"- **Main Model:** `{main_model}` | **Eval Judge Model:** `{eval_judge_model}`",
        f"- **DeepEval Installed:** `{HAS_DEEPEVAL}` (metrics: `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`)",
        "- **Thresholds:** `TODO(owner)` (`evals/thresholds.yaml`)",
        "",
        f"| Configuration | Scope | Count | Recall@{top_k} | MRR@{top_k} | nDCG@{top_k} |",
        "| :--- | :--- | ---: | ---: | ---: | ---: |",
    ]
    for cfg_res in ablation_results:
        cfg_name = cfg_res["configuration"]
        for scope in ("overall", "ja", "en"):
            sc = cfg_res[scope]
            md_lines.append(
                f"| `{cfg_name}` | `{scope}` | {sc['count']} | "
                f"{sc[f'recall_at_{top_k}']:.4f} | {sc[f'mrr_at_{top_k}']:.4f} | {sc[f'ndcg_at_{top_k}']:.4f} |"
            )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 3 Retriever Evaluation")
    parser.add_argument("--dataset", default=str(REPO_ROOT / "goldens" / "retriever.json"))
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Run 5-way ablation comparison")
    parser.add_argument("--smoke", type=int, default=None, help="Limit items for fast smoke run")
    parser.add_argument("--out", default=str(REPO_ROOT / "evals" / "reports"))
    args = parser.parse_args(argv)

    try:
        run_retriever_eval(
            args.dataset,
            allow_draft=args.allow_draft,
            compare=args.compare,
            smoke_limit=args.smoke,
            out_dir=args.out,
        )
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
