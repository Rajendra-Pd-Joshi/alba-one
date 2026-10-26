"""Read-only knowledge document extractors (`kb/extractors.py`).

Converts rows and joins from DBA-controlled PostgreSQL views (`v_kb_*`) or seed
snapshots into bilingual (`ja` and `en`) `KnowledgeDocumentRecord` objects
preserving `source_table`, `source_pk`, `entity_ids`, `acl_tags`, `valid_from`,
`valid_to`, `lang`, and `updated_at`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alba_one.kb.ontology_logic import OntologyCatalog

ALLOWED_EXTRACTION_VIEWS: frozenset[str] = frozenset(
    {
        "v_kb_companies",
        "v_kb_delivery_routes",
        "v_kb_vessels_berths",
        "v_kb_staff_shifts",
        "v_kb_ml_model_releases",
    }
)


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    """Extracted natural-language + structured metadata document ready for PII scrubbing & chunking."""

    doc_id: str
    tenant_id: str
    entity_type: str
    title: str
    text: str
    source_table: str
    source_view: str
    source_pk: str
    entity_ids: list[str]
    acl_tags: list[str]
    valid_from: str
    valid_to: str | None
    updated_at: str
    lang: str
    is_synthetic: bool = True
    structured_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Deterministic SHA-256 hash of document text and ACL metadata for idempotent indexing."""
        payload = (
            f"{self.tenant_id}|{self.source_table}|{self.source_pk}|"
            f"{self.lang}|{self.text}|{'|'.join(sorted(self.acl_tags))}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_readonly_view_sql(view_name: str, incremental_since: str | None = None) -> str:
    """Build a parameterized read-only SQL query against an allowlisted DBA view."""
    if view_name not in ALLOWED_EXTRACTION_VIEWS:
        raise PermissionError(
            f"View '{view_name}' is not in ALLOWED_EXTRACTION_VIEWS. "
            "Extractors may only read DBA-approved views."
        )
    base_sql = f"SELECT * FROM {view_name} WHERE tenant_id = :tenant_id"
    if incremental_since:
        base_sql += " AND updated_at > :incremental_since"
    return base_sql + " ORDER BY source_pk ASC"


def _make_pair(
    tenant_id: str,
    etype: str,
    spec: Any,
    pk: str,
    entity_ids: list[str],
    title_ja: str,
    title_en: str,
    text_ja: str,
    text_en: str,
    meta: dict[str, Any],
    valid_to: str | None = None,
) -> list[KnowledgeDocumentRecord]:
    """Emit paired Japanese (`ja`) and English (`en`) knowledge documents for a single source row."""
    vf = "2026-10-24T00:00:00+09:00"
    ua = "2026-10-24T09:00:00+09:00"
    synth = bool(meta.get("is_synthetic", True))
    return [
        KnowledgeDocumentRecord(
            doc_id=f"doc_{tenant_id}_{etype}_{pk}_{lang}",
            tenant_id=tenant_id,
            entity_type=etype,
            title=title,
            text=body,
            source_table=spec.source_table,
            source_view=spec.source_view,
            source_pk=pk,
            entity_ids=entity_ids,
            acl_tags=list(spec.acl_tags),
            valid_from=vf,
            valid_to=valid_to,
            updated_at=ua,
            lang=lang,
            is_synthetic=synth,
            structured_metadata=meta,
        )
        for lang, title, body in [("ja", title_ja, text_ja), ("en", title_en, text_en)]
    ]


def extract_documents_from_seed_snapshot(
    seed_json_path: str | Path,
    ontology: OntologyCatalog,
    *,
    incremental_since: str | None = None,
) -> list[KnowledgeDocumentRecord]:
    """Convert the demo company's operational rows and joins into bilingual `KnowledgeDocumentRecord`s."""
    raw = json.loads(Path(seed_json_path).read_text(encoding="utf-8"))
    tenant = raw["tenant"]
    tenant_id = str(tenant["id"])
    if tenant_id != ontology.tenant_id:
        raise PermissionError(
            f"Seed tenant '{tenant_id}' does not match ontology tenant '{ontology.tenant_id}'."
        )
    if incremental_since and "2026-10-24T09:00:00+09:00" <= incremental_since:
        return []

    ent = ontology.entities
    docs: list[KnowledgeDocumentRecord] = []

    docs.extend(
        _make_pair(
            tenant_id,
            "company",
            ent["company"],
            tenant_id,
            [tenant_id],
            f"企業定義: {tenant['name_ja']}",
            f"Company Profile: {tenant['name_en']}",
            f"{tenant['name_ja']}（ID: {tenant_id}）はISMS統制下で運航・配送・要員・MLリリースの意思決定OSを運用。",
            f"{tenant['name_en']} (ID: {tenant_id}) operates the ALBA ONE Decision OS under ISMS controls.",
            tenant,
        )
    )

    for r in raw.get("delivery_routes", []):
        pk, code, veh = str(r["id"]), str(r["route_code"]), str(r["vehicle_id"])
        cold_ja = "必須（2〜8℃定温）" if r["cold_chain_required"] else "不要（一般貨物）"
        cold_en = "Mandatory (2-8C)" if r["cold_chain_required"] else "Not required"
        docs.extend(
            _make_pair(
                tenant_id,
                "route",
                ent["route"],
                pk,
                [pk, code, veh],
                f"配送ルート {code}: {r['origin_ja']} → {r['destination_ja']}",
                f"Delivery Route {code}: {r['origin_en']} -> {r['destination_en']}",
                f"配送ルート {code}（{pk}）は {r['origin_ja']} から {r['destination_ja']} へ運行。割当車両 {veh}（{r['vehicle_type']}、最大積載 {r['max_payload_kg']}kg）、SLA {r['sla_hours']}時間以内、定温管理: {cold_ja}。",
                f"Delivery route {code} ({pk}) from {r['origin_en']} to {r['destination_en']} uses vehicle {veh} ({r['vehicle_type']}, max payload {r['max_payload_kg']}kg), SLA {r['sla_hours']}h, cold-chain: {cold_en}.",
                r,
            )
        )
        docs.extend(
            _make_pair(
                tenant_id,
                "equipment",
                ent["equipment"],
                veh,
                [veh, pk],
                f"輸送車両仕様: {veh} ({r['vehicle_type']})",
                f"Vehicle Equipment Spec: {veh} ({r['vehicle_type']})",
                f"車両 {veh}（{r['vehicle_type']}）の最大積載量は {r['max_payload_kg']}kg（ルート {code}）。瞬間風速15.0m/s超過時は荷役停止。",
                f"Vehicle {veh} ({r['vehicle_type']}) has max payload {r['max_payload_kg']}kg on route {code}. Crane transfer halts above 15.0 m/s wind.",
                r,
            )
        )

    for v in raw.get("vessels_berths", []):
        pk, berth = str(v["id"]), str(v["berth_code"])
        docs.extend(
            _make_pair(
                tenant_id,
                "vessel",
                ent["vessel"],
                pk,
                [pk, berth],
                f"船舶・バース計画: {v['vessel_name_ja']} ({berth})",
                f"Vessel & Berth Plan: {v['vessel_name_en']} ({berth})",
                f"船舶 {v['vessel_name_ja']}（{pk}、{v['teu_capacity']} TEU、喫水 {v['draft_meters']}m）は {v['port_ja']}（{berth}）へ {v['eta_jst']} 着岸予定。積載貨物: {v['cargo_type_ja']}。",
                f"Vessel {v['vessel_name_en']} ({pk}, {v['teu_capacity']} TEU, draft {v['draft_meters']}m) arrives at {v['port_en']} ({berth}) at {v['eta_jst']}. Cargo: {v['cargo_type_en']}.",
                v,
                valid_to="2026-11-01T06:00:00+09:00",
            )
        )
        docs.extend(
            _make_pair(
                tenant_id,
                "product",
                ent["product"],
                f"prod_{pk}",
                [f"prod_{pk}", pk],
                f"取扱貨物カテゴリ: {v['cargo_type_ja']}",
                f"Cargo Product Category: {v['cargo_type_en']}",
                f"貨物カテゴリ「{v['cargo_type_ja']}」（{v['vessel_name_ja']}）は2.0〜8.0℃定温維持と着岸後4.0時間以内の配送が必須。",
                f"Cargo '{v['cargo_type_en']}' aboard {v['vessel_name_en']} requires 2.0-8.0C cold chain and delivery within 4.0 hours.",
                v,
            )
        )

    for s in raw.get("staff_shifts", []):
        pk, code = str(s["id"]), str(s["staff_code"])
        docs.extend(
            _make_pair(
                tenant_id,
                "staff",
                ent["staff"],
                pk,
                [pk, code],
                f"要員シフト・労務情報: {code} ({s['qualification']})",
                f"Staff Shift & Overtime Record: {code} ({s['qualification']})",
                f"要員 {code}（氏名: {s['name_ja']}、電話: 090-1234-5678、〒140-0003）は {s['location_ja']} でシフト {s['shift_window_jst']} 担当（資格: {s['qualification']}）。当月残業 {s['overtime_hours_month']}時間（36協定法定上限 {s['max_legal_overtime_hours']}時間）。",
                f"Staff {code} (Name: {s['name_en']}, Phone: 090-1234-5678, Postal: 140-0003) at {s['location_en']} shift {s['shift_window_jst']} ({s['qualification']}). Monthly overtime is {s['overtime_hours_month']}h (Article 36 legal cap {s['max_legal_overtime_hours']}h).",
                s,
            )
        )

    for m in raw.get("ml_model_releases", []):
        pk, ver = str(m["id"]), str(m["version_tag"])
        docs.extend(
            _make_pair(
                tenant_id,
                "model_release",
                ent["model_release"],
                pk,
                [pk, ver, str(m["experiment_id"])],
                f"MLモデルリリース評価: {m['model_family']} {ver}",
                f"ML Model Release Benchmark: {m['model_family']} {ver}",
                f"モデル {m['model_family']} {ver}（実験 {m['experiment_id']}、{m['release_status']}）：{m['summary_ja']} 指標 nDCG@10={m['ndcg_at_10']}、p95={m['p95_latency_ms']}ms、幻覚率={m['hallucination_rate']}。",
                f"Model {m['model_family']} {ver} (Experiment {m['experiment_id']}, {m['release_status']}): {m['summary_en']} Metrics: nDCG@10={m['ndcg_at_10']}, p95 latency={m['p95_latency_ms']}ms, hallucination_rate={m['hallucination_rate']}.",
                m,
            )
        )

    return docs
