"""Stage 2: Multi-Query Rewriter (`retrieval/query_rewriter.py`).

Generates up to `N` query variants (configurable via `QUERY_REWRITE_COUNT`, default 4):
1. `paraphrase`: Domain-normalized paraphrase in the user's language.
2. `decomposition`: Sub-question targeting specific operational metrics/constraints.
3. `step_back`: Higher-level principle/policy query (SLA, 36協定, SLO rules).
4. `cross_lingual`: Cross-lingual translation (`ja` <-> `en`) so mixed-language KB documents are matched.
Deduplicates all variants while preserving order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Bidirectional domain glossary map for cross-lingual (JP <-> EN) query expansion
_JP_TO_EN_TERMS: dict[str, str] = {
    "アルバ・オーロラ号": "MV ALBA AURORA vessel_alba_aurora",
    "アルバ・ホライゾン号": "MV ALBA HORIZON vessel_alba_horizon",
    "アルバ・クレスト号": "MV ALBA CREST vessel_alba_crest",
    "大井第3バース": "Tokyo Port Oi Berth 3 TYO-OI-B3",
    "本牧": "Yokohama Honmoku YOK-HM-D1",
    "医薬品": "Pharma Cold-Chain 2-8C SLA",
    "定温": "reefer cold-chain VH-REEFER-08",
    "配送ルート": "delivery route RT-KNT-101 RT-KNT-102",
    "残業": "overtime hours Article 36 legal cap",
    "36協定": "Article 36 max_legal_overtime_hours 45.0h",
    "要員": "staff shift qualification STF-401 STF-402",
    "モデル": "ML model release eta-demand-forecaster v2.4.0-rc1 nDCG@10",
    "レイテンシ": "p95 latency ms SLO",
}

_EN_TO_JP_TERMS: dict[str, str] = {
    "aurora": "アルバ・オーロラ号 TYO-OI-B3 医薬品定温コンテナ",
    "horizon": "アルバ・ホライゾン号 横浜港本牧D1バース YOK-HM-D1",
    "crest": "アルバ・クレスト号 東京港大井第4バース TYO-OI-B4",
    "route": "配送ルート RT-KNT-101 RT-KNT-102 最大積載量 SLA",
    "reefer": "定温車両 VH-REEFER-08 コールドチェーン",
    "overtime": "当月残業時間 36協定法定上限 45時間 STF-401 STF-402",
    "staff": "要員シフト 保有資格 残業時間 STF-401 STF-402",
    "model": "MLモデルリリース eta-demand-forecaster v2.4.0-rc1 nDCG@10 幻覚率",
    "latency": "p95レイテンシ 600ms SLO",
}


@dataclass(frozen=True)
class RewrittenQuerySet:
    """Deduplicated multi-query rewrite bundle."""

    original_query: str
    variants: list[dict[str, str]] = field(default_factory=list)
    ja_queries: list[str] = field(default_factory=list)
    en_queries: list[str] = field(default_factory=list)
    all_queries: list[str] = field(default_factory=list)


def _translate_cross_lingual(query: str, source_lang: str) -> str:
    """Synthesize a cross-lingual search variant using domain entity & glossary mappings."""
    q_lower = query.lower()
    if source_lang == "ja":
        matched_en = [en_val for jp_key, en_val in _JP_TO_EN_TERMS.items() if jp_key in query]
        if matched_en:
            return f"Decision OS KB lookup: {' '.join(matched_en)} ({query})"
        return f"ALBA ONE operational specification and constraints for: {query}"

    matched_ja = [jp_val for en_key, jp_val in _EN_TO_JP_TERMS.items() if en_key in q_lower]
    if matched_ja:
        return f"意思決定OS ナレッジ検索: {' '.join(matched_ja)} ({query})"
    return f"業務の意味とデータの接続・判断条件: {query}"


def rewrite_queries(
    query: str,
    *,
    lang: str = "ja",
    num_variants: int = 4,
    clarification_answers: list[str] | None = None,
    explicit_assumptions: list[str] | None = None,
    thread_memory: dict[str, Any] | None = None,
) -> RewrittenQuerySet:
    """Generate and deduplicate `num_variants` query variants (paraphrase, decomposition, step-back, cross-lingual)."""
    base = query.strip()
    extra_context = " ".join(clarification_answers or [])
    mem_hint = str((thread_memory or {}).get("active_entity", "")).strip()
    enriched_base = " ".join(p for p in [base, extra_context, mem_hint] if p).strip()

    if lang == "ja":
        candidates = [
            ("paraphrase", "ja", f"{enriched_base} 業務定義・対象ID・数値条件"),
            ("decomposition", "ja", f"{base} 関連する配送ルート・船舶バース・要員残業・モデル評価指標"),
            ("step_back", "ja", f"{base} SLA上限・36協定・本番昇格SLOなどの判断制約ルール"),
            ("cross_lingual", "en", _translate_cross_lingual(enriched_base, "ja")),
        ]
    else:
        candidates = [
            ("paraphrase", "en", f"{enriched_base} entity IDs, specifications, and target metrics"),
            ("decomposition", "en", f"{base} delivery routes, vessel berths, staff overtime, and ML benchmarks"),
            ("step_back", "en", f"{base} operational SLA constraints, Article 36 labor limits, and release SLO rules"),
            ("cross_lingual", "ja", _translate_cross_lingual(enriched_base, "en")),
        ]

    seen: set[str] = set()
    variants: list[dict[str, str]] = []
    ja_list: list[str] = []
    en_list: list[str] = []
    all_list: list[str] = []

    # Always include the original query first
    seen.add(base.lower())
    all_list.append(base)
    if lang == "ja":
        ja_list.append(base)
    else:
        en_list.append(base)

    for kind, v_lang, text in candidates:
        if len(variants) >= num_variants:
            break
        norm = text.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            variants.append({"kind": kind, "lang": v_lang, "query": text.strip()})
            all_list.append(text.strip())
            if v_lang == "ja":
                ja_list.append(text.strip())
            else:
                en_list.append(text.strip())

    return RewrittenQuerySet(
        original_query=base,
        variants=variants,
        ja_queries=ja_list,
        en_queries=en_list,
        all_queries=all_list,
    )
