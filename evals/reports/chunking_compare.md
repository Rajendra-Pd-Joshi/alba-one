# ALBA ONE — Chunking Strategy Comparison Report

- **Dataset:** `goldens/chunking_smoke.json` (6 items; 6 drafts)
- **Selected Default Strategy:** `parent_child`

| Strategy | Total Chunks | Avg Chars | Recall@3 | MRR@3 | nDCG@3 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `recursive_ja` | 28 | 154.4 | 1.0000 | 1.0000 | 1.0000 |
| `semantic` | 39 | 100.3 | 1.0000 | 1.0000 | 1.0000 |
| `parent_child` | 33 | 173.1 | 1.0000 | 1.0000 | 1.0000 |
| `structure_aware` | 26 | 654.8 | 1.0000 | 1.0000 | 1.0000 |
