"""Japanese + English full-text search (FTS) tokenizer and BM25/tsvector scorer (`kb/fts.py`).

Uses `SudachiPy` (`sudachipy` + `sudachidict-core`, SplitMode.C) when installed on
the developer machine/container, and falls back to a deterministic Japanese character
bigram + script-run tokenizer when running in environments without compiled C wheels.
Both paths produce space-delimited tokens stored in `kb_chunks.tokenized_text` for
PostgreSQL `to_tsvector('simple', tokenized_text) @@ plainto_tsquery('simple', :q)`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

try:
    from sudachipy import dictionary as _sudachi_dict  # type: ignore[import-not-found]
    from sudachipy import tokenizer as _sudachi_tok  # type: ignore[import-not-found]

    _SUDACHI_TOKENIZER = _sudachi_dict.Dictionary().create()
    _SUDACHI_MODE = _sudachi_tok.Tokenizer.SplitMode.C
    HAS_SUDACHI = True
except Exception:
    _SUDACHI_TOKENIZER = None
    _SUDACHI_MODE = None
    HAS_SUDACHI = False

# Matches ASCII alphanumeric identifiers (e.g. RT-KNT-101, VH-REEFER-08, v2.4.0-rc1, nDCG@10)
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*")
# Matches contiguous Kanji or Katakana runs
_CJK_RUN_RE = re.compile(r"[\u30A0-\u30FF]+|[\u4E00-\u9FFF]+")


def tokenize_for_fts(text: str) -> list[str]:
    """Tokenize Japanese and English text into normalized search terms."""
    if not text or not text.strip():
        return []
    normalized = unicodedata.normalize("NFKC", text).lower()

    if HAS_SUDACHI and _SUDACHI_TOKENIZER is not None:
        morphemes = _SUDACHI_TOKENIZER.tokenize(normalized, _SUDACHI_MODE)
        tokens = [m.normalized_form().strip() for m in morphemes if m.surface().strip()]
        return [t for t in tokens if len(t) > 1 or t.isalnum()]

    tokens: list[str] = []
    # 1. Extract all ASCII/alphanumeric codes & English words
    for m in _ASCII_TOKEN_RE.finditer(normalized):
        tok = m.group(0).strip(".-")
        if tok:
            tokens.append(tok)
            if "-" in tok:
                tokens.extend(p for p in tok.split("-") if p)

    # 2. Extract Kanji/Katakana words and overlapping character bigrams (pg_bigm style)
    for m in _CJK_RUN_RE.finditer(normalized):
        run = m.group(0)
        tokens.append(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                tokens.append(run[i : i + 2])

    return tokens


def build_tokenized_tsvector_string(text: str) -> str:
    """Return a space-delimited token string for `kb_chunks.tokenized_text`."""
    return " ".join(tokenize_for_fts(text))


def score_fts_match(query: str, chunk_tokenized_text: str) -> float:
    """Compute a normalized BM25-style lexical relevance score in [0, 1] for FTS ranking."""
    q_tokens = tokenize_for_fts(query)
    if not q_tokens or not chunk_tokenized_text:
        return 0.0
    doc_tokens = chunk_tokenized_text.split()
    if not doc_tokens:
        return 0.0

    doc_counts = Counter(doc_tokens)
    matched = 0.0
    for qt in set(q_tokens):
        freq = doc_counts.get(qt, 0)
        if freq > 0:
            matched += 1.0 + math.log1p(freq)

    max_possible = len(set(q_tokens)) * (1.0 + math.log1p(3))
    return round(min(1.0, matched / max(1.0, max_possible)), 4)
