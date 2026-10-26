# ALBA ONE — Phase 3 Retriever Evaluation Report

- **Dataset:** `goldens/retriever.json` (60/60 items evaluated; 60 drafts)
- **Main Model:** `gpt-4o-2024-08-06` | **Eval Judge Model:** `claude-3-5-sonnet-20241022`
- **DeepEval Installed:** `False` (metrics: `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`)
- **Thresholds:** `TODO(owner)` (`evals/thresholds.yaml`)

| Configuration | Scope | Count | Recall@5 | MRR@5 | nDCG@5 |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `dense_only` | `overall` | 60 | 0.4278 | 0.4367 | 0.3924 |
| `dense_only` | `ja` | 30 | 0.0333 | 0.0067 | 0.0129 |
| `dense_only` | `en` | 30 | 0.8222 | 0.8667 | 0.7718 |
| `keyword_only` | `overall` | 60 | 0.9611 | 0.9450 | 0.9158 |
| `keyword_only` | `ja` | 30 | 1.0000 | 1.0000 | 0.9816 |
| `keyword_only` | `en` | 30 | 0.9222 | 0.8900 | 0.8501 |
| `hybrid` | `overall` | 60 | 0.8556 | 0.8394 | 0.8038 |
| `hybrid` | `ja` | 30 | 0.7722 | 0.7222 | 0.7135 |
| `hybrid` | `en` | 30 | 0.9389 | 0.9567 | 0.8942 |
| `hybrid_rerank` | `overall` | 60 | 0.9111 | 0.9222 | 0.8939 |
| `hybrid_rerank` | `ja` | 30 | 0.8333 | 0.8667 | 0.8321 |
| `hybrid_rerank` | `en` | 30 | 0.9889 | 0.9778 | 0.9557 |
| `hybrid_rerank_corrective` | `overall` | 60 | 0.9139 | 0.9139 | 0.8926 |
| `hybrid_rerank_corrective` | `ja` | 30 | 0.8389 | 0.8500 | 0.8296 |
| `hybrid_rerank_corrective` | `en` | 30 | 0.9889 | 0.9778 | 0.9557 |
