-- =============================================================================
-- ALBA ONE — DBA-Controlled Read-Only Extraction Views (Phase 2 Requirement 2)
--
-- The ingestion pipeline NEVER queries raw operational tables directly with a
-- read-write role. Instead, the DBA exposes curated read-only views (`v_kb_*`)
-- with explicit columns, validity timestamps (`valid_from`, `valid_to`), and
-- `updated_at` watermarks for incremental indexing.
-- =============================================================================

BEGIN;

CREATE OR REPLACE VIEW v_kb_companies AS
SELECT
    id AS source_pk,
    id AS tenant_id,
    name_ja,
    name_en,
    isms_enforced,
    is_synthetic,
    created_at AS valid_from,
    NULL::TIMESTAMPTZ AS valid_to,
    created_at AS updated_at
FROM tenants;

CREATE OR REPLACE VIEW v_kb_delivery_routes AS
SELECT
    id AS source_pk,
    tenant_id,
    route_code,
    origin_ja,
    origin_en,
    destination_ja,
    destination_en,
    vehicle_id,
    vehicle_type,
    max_payload_kg,
    sla_hours,
    cold_chain_required,
    is_synthetic,
    created_at AS valid_from,
    NULL::TIMESTAMPTZ AS valid_to,
    created_at AS updated_at
FROM demo_delivery_routes;

CREATE OR REPLACE VIEW v_kb_vessels_berths AS
SELECT
    id AS source_pk,
    tenant_id,
    vessel_name_ja,
    vessel_name_en,
    berth_code,
    port_ja,
    port_en,
    cargo_type_ja,
    cargo_type_en,
    teu_capacity,
    eta_jst,
    draft_meters,
    is_synthetic,
    created_at AS valid_from,
    (eta_jst + INTERVAL '7 days') AS valid_to,
    created_at AS updated_at
FROM demo_vessels_berths;

CREATE OR REPLACE VIEW v_kb_staff_shifts AS
SELECT
    id AS source_pk,
    tenant_id,
    staff_code,
    name_ja,
    name_en,
    qualification,
    location_ja,
    location_en,
    shift_window_jst,
    overtime_hours_month,
    max_legal_overtime_hours,
    is_synthetic,
    created_at AS valid_from,
    NULL::TIMESTAMPTZ AS valid_to,
    created_at AS updated_at
FROM demo_staff_shifts;

CREATE OR REPLACE VIEW v_kb_ml_model_releases AS
SELECT
    id AS source_pk,
    tenant_id,
    model_family,
    version_tag,
    experiment_id,
    summary_ja,
    summary_en,
    ndcg_at_10,
    p95_latency_ms,
    hallucination_rate,
    release_status,
    is_synthetic,
    created_at AS valid_from,
    NULL::TIMESTAMPTZ AS valid_to,
    created_at AS updated_at
FROM demo_ml_model_releases;

COMMIT;
