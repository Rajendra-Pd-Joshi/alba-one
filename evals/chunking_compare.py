"""Chunking strategy comparison evaluation (`evals/chunking_compare.py`).

Runnable as:
    uv run python -m evals.chunking_compare --dataset goldens/chunking_smoke.json --allow-draft [--out evals/reports/]

Compares all 4 chunking strategies (`recursive_ja`, `semantic`, `parent_child`,
`structure_aware`) on the demo knowledge base using the golden dataset, reporting:
- Chunk count & average character/token length
- Recall@3, MRR@3, and nDCG@3 by matching retrieved `entity_ids` against `expected_entity_ids`
- Refuses to run on `status == "draft"` items unless `--allow-draft` is passed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "apps" / "api" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from alba_one.kb.chunkers import SUPPORTED_CHUNKING_STRATEGIES, chunk_document
from alba_one.kb.extractors import extract_documents_from_seed_snapshot
from alba_one.kb.fts import build_tokenized_tsvector_string, score_fts_match
from alba_one.kb.ontology_logic import load_ontology_catalog
from alba_one.kb.pii import PIIRedactor


def evaluate_strategy(
    strategy: str,
    goldens: list[dict[str, Any]],
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    """Run extraction, PII scrubbing, chunking, and FTS retrieval for one strategy."""
    ontology = load_ontology_catalog(REPO_ROOT / "config" / "ontology_demo.yaml")
    docs = extract_documents_from_seed_snapshot(
        REPO_ROOT / "infra" / "seed" / "synthetic_demo_data.json",
        ontology,
    )
    redactor = PIIRedactor()

    chunks = []
    for doc in docs:
        redacted = redactor.redact(doc.text).redacted_text
        for chk in chunk_document(doc, redacted, strategy=strategy):
            chunks.append((chk, build_tokenized_tsvector_string(chk.text)))

    recalls: list[float] = []
    mrrs: list[float] = []
    ndcgs: list[float] = []

    for item in goldens:
        query = str(item["input"])
        lang = str(item["lang"])
        expected_entities = set(item.get("expected_entity_ids", []))

        scored = []
        for chk, tok_str in chunks:
            if chk.lang != lang:
                continue
            score = score_fts_match(query, tok_str)
            scored.append((score, chk))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for _, c in scored[:top_k]]

        retrieved_entities: set[str] = set()
        first_hit_rank: int | None = None
        dcg = 0.0
        for rank_idx, chk in enumerate(top_chunks, start=1):
            ent_set = set(chk.entity_ids)
            retrieved_entities |= ent_set
            if ent_set & expected_entities:
                if first_hit_rank is None:
                    first_hit_rank = rank_idx
                dcg += 1.0 / math.log2(rank_idx + 1)

        recall = (
            len(retrieved_entities & expected_entities) / len(expected_entities)
            if expected_entities
            else 1.0
        )
        mrr = (1.0 / first_hit_rank) if first_hit_rank is not None else 0.0
        idcg = 1.0  # Ideal hit at rank 1
        ndcg = min(1.0, dcg / idcg)

        recalls.append(recall)
        mrrs.append(mrr)
        ndcgs.append(ndcg)

    avg_chars = sum(len(c.text) for c, _ in chunks) / max(1, len(chunks))
    return {
        "strategy": strategy,
        "total_chunks": len(chunks),
        "avg_chunk_chars": round(avg_chars, 1),
        f"recall_at_{top_k}": round(sum(recalls) / max(1, len(recalls)), 4),
        f"mrr_at_{top_k}": round(sum(mrrs) / max(1, len(mrrs)), 4),
        f"ndcg_at_{top_k}": round(sum(ndcgs) / max(1, len(ndcgs)), 4),
    }


def run_chunking_comparison(
    dataset_path: str | Path,
    *,
    allow_draft: bool = False,
    out_dir: str | Path = REPO_ROOT / "evals" / "reports",
) -> dict[str, Any]:
    """Validate golden dataset draft status and compare all 4 chunking strategies."""
    items = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    draft_count = sum(1 for item in items if item.get("status") == "draft")
    print(f"[chunking_compare] Loaded {len(items)} items ({draft_count} with status='draft').")

    if draft_count > 0 and not allow_draft:
        raise RuntimeError(
            f"Refusing to run on {draft_count} draft golden items. Pass --allow-draft to run."
        )

    results = [evaluate_strategy(strat, items) for strat in SUPPORTED_CHUNKING_STRATEGIES]
    report = {
        "eval": "chunking_compare",
        "dataset": str(dataset_path),
        "total_items": len(items),
        "draft_items": draft_count,
        "allow_draft": allow_draft,
        "default_recommended_strategy": "parent_child",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "strategies": results,
    }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    json_file = out_path / "chunking_compare.json"
    md_file = out_path / "chunking_compare.md"

    json_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# ALBA ONE — Chunking Strategy Comparison Report",
        "",
        f"- **Dataset:** `{dataset_path}` ({len(items)} items; {draft_count} drafts)",
        "- **Selected Default Strategy:** `parent_child`",
        "",
        "| Strategy | Total Chunks | Avg Chars | Recall@3 | MRR@3 | nDCG@3 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in results:
        md_lines.append(
            f"| `{r['strategy']}` | {r['total_chunks']} | {r['avg_chunk_chars']} | "
            f"{r['recall_at_3']:.4f} | {r['mrr_at_3']:.4f} | {r['ndcg_at_3']:.4f} |"
        )
    md_file.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare ALBA ONE KB chunking strategies.")
    parser.add_argument("--dataset", required=True, help="Path to golden JSON dataset")
    parser.add_argument("--allow-draft", action="store_true", help="Allow running on draft items")
    parser.add_argument("--out", default=str(REPO_ROOT / "evals" / "reports"), help="Output directory")
    args = parser.parse_args(argv)

    try:
        run_chunking_comparison(args.dataset, allow_draft=args.allow_draft, out_dir=args.out)
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
