# ADR 0002: Japanese Full-Text Search Tokenization in PostgreSQL (`SudachiPy` + `'simple'` tsvector vs. `pg_bigm`)

- **Status:** Accepted (Phase 2 — Knowledge Base and Ingestion)
- **Date:** 2026-10-24
- **Owners:** ALBACONNECT Engineering

## Context
ALBA ONE stores knowledge documents and chunk text in on-premise PostgreSQL (`kb_documents` and `kb_chunks`) and requires cross-lingual (Japanese + English) keyword search alongside Pinecone dense vector retrieval. Standard PostgreSQL (`postgres:16-alpine`) lacks a built-in Japanese morphological analyzer because Japanese does not use spaces between words.

We evaluated two approaches specified in the master prompt:
1. **Application-side Japanese tokenization (`SudachiPy` / `sudachidict-core` with CJK bigram fallback) stored in `kb_chunks.tokenized_text` + PostgreSQL built-in `to_tsvector('simple', tokenized_text)` and GIN index.**
2. **PostgreSQL C extension `pg_bigm` compiled into a custom PostgreSQL container image.**

## Comparison

| Criterion | **`SudachiPy` + `to_tsvector('simple', ...)` (Selected)** | **`pg_bigm` PostgreSQL Extension** |
| :--- | :--- | :--- |
| **On-Premise DBA Portability** | Works on any stock PostgreSQL 16 (RDS, Cloud SQL, or on-prem VM) with zero superuser C-extension installation required | Requires compiling/installing `pg_bigm.so` and `shared_preload_libraries = 'pg_bigm'` on the database host |
| **Domain Compound Nouns & Codes** | `SudachiPy` `SplitMode.C` preserves compound business terms (`医薬品定温コンテナ`, `ガントリークレーン`) while splitting alphanumeric codes (`RT-KNT-101`, `VH-REEFER-08`) | Pure 2-character bigrams produce high false-positive matches on single-kanji overlaps |
| **Bilingual (JP + EN) Ranking** | Native `ts_rank_cd` over `'simple'` dictionary handles both Japanese morphemes and English stems in one GIN index | Requires `LIKE` / `=%` similarity operators separate from `tsvector` |

## Decision
We select **`SudachiPy` (`SplitMode.C`) + CJK bigram expansion written to `kb_chunks.tokenized_text` (`kb/fts.py`)** indexed with PostgreSQL's built-in `'simple'` text search configuration. This guarantees zero-friction deployment across stock PostgreSQL 16 (`postgres:16-alpine`), AWS RDS, GCP Cloud SQL, and locked-down on-premise enterprise Postgres servers where DBAs prohibit third-party C extensions.
