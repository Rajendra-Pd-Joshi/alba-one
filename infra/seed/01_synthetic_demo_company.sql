-- =============================================================================
-- ALBA ONE — Synthetic Demo Company Seed (Phase 1 Requirement 7)
-- Tenant: tenant_alba_demo (ALBA Logistics & Maritime Demo Corp / アルバ物流海運デモ株式会社)
--
-- IMPORTANT (Principle 10 — Honesty):
-- All rows in this file are 100% synthetic data for demonstration and testing.
-- Every single table and row carries `is_synthetic = TRUE` and `tenant_id = 'tenant_alba_demo'`.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Operational Domain Tables for the Demo Company (Pillar 1 & Pillar 2)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS demo_delivery_routes (
    id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    route_code VARCHAR(64) NOT NULL,
    origin_ja VARCHAR(255) NOT NULL,
    origin_en VARCHAR(255) NOT NULL,
    destination_ja VARCHAR(255) NOT NULL,
    destination_en VARCHAR(255) NOT NULL,
    vehicle_id VARCHAR(64) NOT NULL,
    vehicle_type VARCHAR(64) NOT NULL,
    max_payload_kg INTEGER NOT NULL,
    sla_hours NUMERIC(5,2) NOT NULL,
    cold_chain_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_vessels_berths (
    id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    vessel_name_ja VARCHAR(255) NOT NULL,
    vessel_name_en VARCHAR(255) NOT NULL,
    berth_code VARCHAR(64) NOT NULL,
    port_ja VARCHAR(128) NOT NULL,
    port_en VARCHAR(128) NOT NULL,
    cargo_type_ja VARCHAR(128) NOT NULL,
    cargo_type_en VARCHAR(128) NOT NULL,
    teu_capacity INTEGER NOT NULL,
    eta_jst TIMESTAMPTZ NOT NULL,
    draft_meters NUMERIC(4,2) NOT NULL,
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_staff_shifts (
    id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    staff_code VARCHAR(64) NOT NULL,
    name_ja VARCHAR(128) NOT NULL,
    name_en VARCHAR(128) NOT NULL,
    qualification VARCHAR(128) NOT NULL,
    location_ja VARCHAR(128) NOT NULL,
    location_en VARCHAR(128) NOT NULL,
    shift_window_jst VARCHAR(64) NOT NULL,
    overtime_hours_month NUMERIC(5,2) NOT NULL,
    max_legal_overtime_hours NUMERIC(5,2) NOT NULL DEFAULT 45.0,
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_ml_model_releases (
    id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    model_family VARCHAR(128) NOT NULL,
    version_tag VARCHAR(64) NOT NULL,
    experiment_id VARCHAR(128) NOT NULL,
    summary_ja TEXT NOT NULL,
    summary_en TEXT NOT NULL,
    ndcg_at_10 NUMERIC(5,4) NOT NULL,
    p95_latency_ms NUMERIC(7,2) NOT NULL,
    hallucination_rate NUMERIC(5,4) NOT NULL,
    release_status VARCHAR(32) NOT NULL,
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 2. Seed Core Tenant & Users (all `is_synthetic = TRUE`)
-- -----------------------------------------------------------------------------
INSERT INTO tenants (id, name_ja, name_en, isms_enforced, is_synthetic)
VALUES (
    'tenant_alba_demo',
    'アルバ物流海運デモ株式会社（合成データ）',
    'ALBA Logistics & Maritime Demo Corp (Synthetic)',
    TRUE,
    TRUE
) ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, tenant_id, email, display_name_ja, display_name_en, role, department, permissions, lang, is_synthetic)
VALUES
    ('user_viewer_01', 'tenant_alba_demo', 'viewer@demo.albaconnect.example', '佐藤 健一（閲覧者）', 'Kenichi Sato (Viewer)', 'viewer', 'logistics', '["decisions:read","kb:read","outcomes:read"]'::jsonb, 'ja', TRUE),
    ('user_analyst_01', 'tenant_alba_demo', 'analyst@demo.albaconnect.example', '高橋 美咲（分析担当）', 'Misaki Takahashi (Analyst)', 'analyst', 'maritime_ops', '["decisions:read","decisions:create","kb:read","tools:invoke_readonly","outcomes:read"]'::jsonb, 'ja', TRUE),
    ('user_approver_01', 'tenant_alba_demo', 'approver@demo.albaconnect.example', '鈴木 誠（運航統括責任者）', 'Makoto Suzuki (Operations Approver)', 'approver', 'executive_ops', '["decisions:read","decisions:create","decisions:approve","kb:read","kb:writeback","outcomes:review"]'::jsonb, 'ja', TRUE),
    ('user_admin_01', 'tenant_alba_demo', 'admin@demo.albaconnect.example', '山本 彩（システム管理者）', 'Aya Yamamoto (System Admin)', 'admin', 'it_security', '["decisions:read","decisions:create","decisions:approve","kb:admin","guardrails:admin","evals:run"]'::jsonb, 'en', TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 3. Seed Delivery Routes & Vehicles (配送ルート・車両データ)
-- -----------------------------------------------------------------------------
INSERT INTO demo_delivery_routes (id, tenant_id, route_code, origin_ja, origin_en, destination_ja, destination_en, vehicle_id, vehicle_type, max_payload_kg, sla_hours, cold_chain_required, is_synthetic)
VALUES
    ('route_tk_ym_01', 'tenant_alba_demo', 'RT-KNT-101', '東京大井ふ頭物流センター', 'Tokyo Oi Pier Logistics Hub', '横浜本牧ロジスティクス拠点', 'Yokohama Honmoku Logistics Depot', 'VH-REEFER-08', '10t_reefer_truck', 9200, 4.00, TRUE, TRUE),
    ('route_tk_cb_02', 'tenant_alba_demo', 'RT-KNT-102', '東京大井ふ頭物流センター', 'Tokyo Oi Pier Logistics Hub', '千葉湾岸ディストリビューション', 'Chiba Bay Distribution Center', 'VH-DRY-14', '10t_wing_truck', 10500, 5.50, FALSE, TRUE),
    ('route_ng_os_03', 'tenant_alba_demo', 'RT-TKI-204', '名古屋港飛島コンテナ基地', 'Nagoya Port Tobishima Terminal', '大阪南港クロスドック', 'Osaka South Port Cross-Dock', 'VH-REEFER-19', '10t_reefer_truck', 9200, 6.00, TRUE, TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 4. Seed Vessels, Berths & Cargo (船舶・バース・貨物データ)
-- -----------------------------------------------------------------------------
INSERT INTO demo_vessels_berths (id, tenant_id, vessel_name_ja, vessel_name_en, berth_code, port_ja, port_en, cargo_type_ja, cargo_type_en, teu_capacity, eta_jst, draft_meters, is_synthetic)
VALUES
    ('vessel_alba_aurora', 'tenant_alba_demo', 'アルバ・オーロラ号', 'MV ALBA AURORA', 'TYO-OI-B3', '東京港大井第3バース', 'Tokyo Port Oi Berth 3', '医薬品定温コンテナ・精密機器', 'Pharma Cold-Chain & Precision Instruments', 4800, '2026-10-25T06:00:00+09:00', 12.40, TRUE),
    ('vessel_alba_horizon', 'tenant_alba_demo', 'アルバ・ホライゾン号', 'MV ALBA HORIZON', 'YOK-HM-D1', '横浜港本牧D1バース', 'Yokohama Port Honmoku Berth D1', '自動車部品・一般消費財', 'Automotive Parts & General Cargo', 6200, '2026-10-25T08:30:00+09:00', 13.80, TRUE),
    ('vessel_alba_crest', 'tenant_alba_demo', 'アルバ・クレスト号', 'MV ALBA CREST', 'TYO-OI-B4', '東京港大井第4バース', 'Tokyo Port Oi Berth 4', '半導体製造装置部材', 'Semiconductor Equipment Modules', 3500, '2026-10-25T14:00:00+09:00', 11.20, TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 5. Seed Staff & Shifts (要員・シフト・36協定残業上限データ)
-- -----------------------------------------------------------------------------
INSERT INTO demo_staff_shifts (id, tenant_id, staff_code, name_ja, name_en, qualification, location_ja, location_en, shift_window_jst, overtime_hours_month, max_legal_overtime_hours, is_synthetic)
VALUES
    ('staff_crane_01', 'tenant_alba_demo', 'STF-401', '渡辺 剛', 'Tsuyoshi Watanabe', 'gantry_crane_lead_hazmat', '東京港大井ふ頭', 'Tokyo Port Oi Pier', '06:00-14:30', 41.50, 45.00, TRUE),
    ('staff_crane_02', 'tenant_alba_demo', 'STF-402', '伊藤 裕子', 'Yuko Ito', 'gantry_crane_lead_coldchain', '東京港大井ふ頭', 'Tokyo Port Oi Pier', '06:00-14:30', 22.00, 45.00, TRUE),
    ('staff_dispatch_03', 'tenant_alba_demo', 'STF-403', '中村 恒一', 'Koichi Nakamura', 'cold_chain_dispatcher', '横浜港本牧ふ頭', 'Yokohama Port Honmoku Pier', '08:00-16:30', 18.50, 45.00, TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 6. Seed ML Model Releases, Experiments & Benchmarks (モデルリリース判断データ)
-- -----------------------------------------------------------------------------
INSERT INTO demo_ml_model_releases (id, tenant_id, model_family, version_tag, experiment_id, summary_ja, summary_en, ndcg_at_10, p95_latency_ms, hallucination_rate, release_status, is_synthetic)
VALUES
    ('ml_eta_predictor_v2_3', 'tenant_alba_demo', 'eta-demand-forecaster', 'v2.3.0-prod', 'exp_2026_09_baseline', '現行本番モデル：台風遅延時のETA予測精度は安定しているが港湾混雑特徴量が未反映。', 'Current production baseline: stable typhoon ETA accuracy but lacks real-time berth congestion features.', 0.8420, 410.00, 0.0180, 'production', TRUE),
    ('ml_eta_predictor_v2_4_rc1', 'tenant_alba_demo', 'eta-demand-forecaster', 'v2.4.0-rc1', 'exp_2026_10_berth_feat', '候補モデルv2.4.0-rc1：バース混雑特徴量を追加しnDCG@10が+3.9pt改善、幻覚率も1.1%に低下。', 'Candidate v2.4.0-rc1: adds berth congestion features, improving nDCG@10 by +3.9pt and lowering hallucination rate to 1.1%.', 0.8810, 445.00, 0.0110, 'candidate', TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 7. Seed Past Decisions, Hypotheses, Approvals & Outcomes (Pillar 3: 結果と知識の運用)
-- -----------------------------------------------------------------------------
INSERT INTO decisions (id, tenant_id, user_id, workflow_domain, query_text, status, verdict, options_compared, rationale, conditions, risks, cited_hypothesis_ids, context_json, lang, is_synthetic)
VALUES
    (
        'dec_synth_vessel_001',
        'tenant_alba_demo',
        'user_analyst_01',
        'vessel_allocation',
        '強風警報発令に伴うアルバ・オーロラ号（医薬品定温コンテナ積載）の東京港大井第3バース着岸優先順位と冷蔵車両VH-REEFER-08の割当判断',
        'outcome_reviewed',
        'approve',
        '["案A: 大井第3バース優先着岸＋伊藤班（残業22h）配置＋VH-REEFER-08直行便", "案B: 横浜本牧D1バースへ回航＋陸送振替"]'::jsonb,
        '医薬品定温コンテナのSLA（4時間以内）と36協定上限（渡辺班は残業41.5hで上限近接）を満たすため、案A（大井第3バース優先着岸＋伊藤班配置）を推奨します。',
        '["瞬間風速15m/s超過時はガントリークレーン作業を一時停止すること", "クレーン責任者は残業時間に余裕のある伊藤裕子（STF-402）を配置すること"]'::jsonb,
        '["横浜回航（案B）を選択した場合、首都高渋滞により医薬品コールドチェーンSLAを1.8時間超過するリスク"]'::jsonb,
        '["hyp_synth_001", "hyp_synth_002"]'::jsonb,
        '{"vessel_id": "vessel_alba_aurora", "route_id": "route_tk_ym_01"}'::jsonb,
        'ja',
        TRUE
    ),
    (
        'dec_synth_model_002',
        'tenant_alba_demo',
        'user_admin_01',
        'model_release',
        'Should we promote eta-demand-forecaster v2.4.0-rc1 to production ahead of the Q4 peak maritime season?',
        'outcome_reviewed',
        'approve',
        '["Option A: Canary rollout (20% traffic for 48h) then full cutover to v2.4.0-rc1", "Option B: Hold on v2.3.0-prod until latency is under 400ms"]'::jsonb,
        'v2.4.0-rc1 improves nDCG@10 from 0.8420 to 0.8810 and cuts hallucination rate from 1.8% to 1.1%, while p95 latency (445ms) remains well within the 600ms SLO.',
        '["Run 20% canary for 48 hours on Tokyo/Yokohama routes", "Auto-rollback if p95 latency exceeds 600ms"]'::jsonb,
        '["Slight +35ms p95 latency increase compared to v2.3.0-prod"]'::jsonb,
        '["hyp_synth_003"]'::jsonb,
        '{"candidate_model": "ml_eta_predictor_v2_4_rc1", "baseline_model": "ml_eta_predictor_v2_3"}'::jsonb,
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO hypotheses (id, tenant_id, decision_id, statement, stance, rationale, evidence_json, assumptions, risks, confidence_score, confidence_json, lang, is_synthetic)
VALUES
    (
        'hyp_synth_001',
        'tenant_alba_demo',
        'dec_synth_vessel_001',
        '案A（大井第3バース優先着岸＋VH-REEFER-08割当）により医薬品定温コンテナの4時間SLAを遵守できる。',
        'support',
        'RT-KNT-101の標準所要時間は4.0時間であり、定温車両VH-REEFER-08（最大積載9,200kg）が大井ふ頭で待機中である。',
        '[{"kind": "kb", "ref_id": "chunk_synth_001", "quote_span": "RT-KNT-101（大井ふ頭→横浜本牧）は定温車両VH-REEFER-08によりSLA 4.0時間以内での配送が規定されている。"}]'::jsonb,
        '["午前6時の着岸時に瞬間風速が15m/s未満であること"]'::jsonb,
        '["強風継続による荷役開始遅延リスク"]'::jsonb,
        0.88,
        '{"score": 0.88, "evidence_strength": 0.92, "coverage": 0.85, "consistency": 0.87, "judge_notes": "配送ルート規定およびバース水深条件（12.4m）と整合。"}'::jsonb,
        'ja',
        TRUE
    ),
    (
        'hyp_synth_002',
        'tenant_alba_demo',
        'dec_synth_vessel_001',
        'クレーン責任者に渡辺剛（STF-401）を割り当てると月間残業45時間上限（36協定）に抵触する恐れがある。',
        'oppose',
        'STF-401の当月累計残業は41.5時間であり、悪天候対応で4時間超過すると45時間上限を上回るため、残業22.0時間の伊藤裕子（STF-402）への変更が必要。',
        '[{"kind": "kb", "ref_id": "chunk_synth_002", "quote_span": "STF-401（渡辺剛）の当月残業実績は41.5h（法定上限45.0h）、STF-402（伊藤裕子）は22.0h（定温コンテナ荷役資格保有）。"}]'::jsonb,
        '["シフト変更が前日20時までに承認されること"]'::jsonb,
        '["労務コンプライアンス違反リスク"]'::jsonb,
        0.93,
        '{"score": 0.93, "evidence_strength": 0.96, "coverage": 0.90, "consistency": 0.93, "judge_notes": "勤怠テーブルの数値根拠が明確。"}'::jsonb,
        'ja',
        TRUE
    ),
    (
        'hyp_synth_003',
        'tenant_alba_demo',
        'dec_synth_model_002',
        'Promoting eta-demand-forecaster v2.4.0-rc1 via canary rollout improves berth ETA accuracy without violating latency SLOs.',
        'support',
        'Offline evaluation exp_2026_10_berth_feat shows nDCG@10=0.8810 (+0.0390 over baseline) and p95 latency=445ms (<600ms threshold).',
        '[{"kind": "kb", "ref_id": "chunk_synth_003", "quote_span": "Experiment exp_2026_10_berth_feat achieved nDCG@10 of 0.8810 and hallucination rate of 0.0110 at 445ms p95 latency."}]'::jsonb,
        '["Canary traffic mirrors peak port congestion distribution"]'::jsonb,
        '["Tail latency spikes if Redis feature store cache misses"]'::jsonb,
        0.86,
        '{"score": 0.86, "evidence_strength": 0.90, "coverage": 0.82, "consistency": 0.86, "judge_notes": "Benchmark metrics directly verified from demo_ml_model_releases."}'::jsonb,
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO approvals (id, tenant_id, decision_id, approver_id, action, reason, edited_conditions, lang, is_synthetic)
VALUES
    (
        'app_synth_001',
        'tenant_alba_demo',
        'dec_synth_vessel_001',
        'user_approver_01',
        'approve',
        '医薬品SLA遵守および36協定順守の観点から案A（大井第3バース＋伊藤班配置）を承認。',
        '["瞬間風速15m/s超過時は即座に荷役中断し運航統括へ連絡すること"]'::jsonb,
        'ja',
        TRUE
    ),
    (
        'app_synth_002',
        'tenant_alba_demo',
        'dec_synth_model_002',
        'user_approver_01',
        'approve',
        'Approved 20% canary rollout of v2.4.0-rc1 with automatic rollback guard at 600ms p95.',
        '["Monitor p95 latency and hallucination rate every 6 hours during 48h canary"]'::jsonb,
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO outcomes (id, tenant_id, decision_id, measured_result, variance_reason, reviewed_by, writeback_chunk_id, lang, is_synthetic)
VALUES
    (
        'out_synth_001',
        'tenant_alba_demo',
        'dec_synth_vessel_001',
        '大井第3バース着岸後3.4時間で横浜本牧拠点へ定温配送完了（SLA 4.0時間以内達成）。伊藤班の残業は+1.5時間（累計23.5h）で労務基準内。',
        '計画比-0.6時間短縮。事前バース優先割当によりゲート待機時間が削減されたため。',
        'user_approver_01',
        'chunk_synth_001',
        'ja',
        TRUE
    ),
    (
        'out_synth_002',
        'tenant_alba_demo',
        'dec_synth_model_002',
        '48h canary completed with 0 rollbacks; production ETA error dropped by 14.2% and p95 latency averaged 438ms.',
        'Variance of -7ms vs benchmark due to Redis exact-match feature caching in production.',
        'user_admin_01',
        'chunk_synth_003',
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO kb_documents (id, tenant_id, title, pillar, source_table, entity_ids, acl_tags, content_hash, metadata_json, lang, is_synthetic)
VALUES
    (
        'doc_synth_ops_001',
        'tenant_alba_demo',
        '東京港・横浜港 定温コンテナ配送およびバース割当規定（合成データ）',
        'business_meaning_and_data',
        'demo_delivery_routes',
        '["route_tk_ym_01", "vessel_alba_aurora", "VH-REEFER-08"]'::jsonb,
        '["role:viewer", "role:analyst", "role:approver", "role:admin"]'::jsonb,
        'a1b2c3d4e5f60001',
        '{"domain": "maritime_logistics", "synthetic": true}'::jsonb,
        'ja',
        TRUE
    ),
    (
        'doc_synth_ml_002',
        'tenant_alba_demo',
        'ETA Demand Forecaster v2.4 Release Benchmark Report (Synthetic)',
        'workflow_decision_support',
        'demo_ml_model_releases',
        '["ml_eta_predictor_v2_3", "ml_eta_predictor_v2_4_rc1"]'::jsonb,
        '["role:analyst", "role:approver", "role:admin"]'::jsonb,
        'a1b2c3d4e5f60002',
        '{"domain": "model_release", "synthetic": true}'::jsonb,
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO kb_chunks (id, tenant_id, document_id, chunk_index, text, tokenized_text, source_table, entity_ids, acl_tags, pinecone_vector_id, lang, is_synthetic)
VALUES
    (
        'chunk_synth_001',
        'tenant_alba_demo',
        'doc_synth_ops_001',
        0,
        'RT-KNT-101（大井ふ頭→横浜本牧）は定温車両VH-REEFER-08によりSLA 4.0時間以内での配送が規定されている。アルバ・オーロラ号（喫水12.4m）は東京港大井第3バース（TYO-OI-B3）に着岸可能。',
        'RT-KNT-101 大井 ふ頭 横浜 本牧 定温 車両 VH-REEFER-08 SLA 4.0 時間 以内 配送 規定 アルバ オーロラ 号 喫水 12.4 m 東京 港 大井 第 3 バース 着岸 可能',
        'demo_delivery_routes',
        '["route_tk_ym_01", "vessel_alba_aurora", "VH-REEFER-08"]'::jsonb,
        '["role:viewer", "role:analyst", "role:approver", "role:admin"]'::jsonb,
        'vec_synth_001',
        'ja',
        TRUE
    ),
    (
        'chunk_synth_002',
        'tenant_alba_demo',
        'doc_synth_ops_001',
        1,
        'STF-401（渡辺剛）の当月残業実績は41.5h（法定上限45.0h）、STF-402（伊藤裕子）は22.0h（定温コンテナ荷役資格保有）。36協定上限超過を防ぐため残業40h超の要員は悪天候シフトから除外する。',
        'STF-401 渡辺 剛 当月 残業 実績 41.5 h 法定 上限 45.0 h STF-402 伊藤 裕子 22.0 h 定温 コンテナ 荷役 資格 保有 36 協定 上限 超過 除外',
        'demo_staff_shifts',
        '["staff_crane_01", "staff_crane_02"]'::jsonb,
        '["role:analyst", "role:approver", "role:admin"]'::jsonb,
        'vec_synth_002',
        'ja',
        TRUE
    ),
    (
        'chunk_synth_003',
        'tenant_alba_demo',
        'doc_synth_ml_002',
        0,
        'Experiment exp_2026_10_berth_feat achieved nDCG@10 of 0.8810 and hallucination rate of 0.0110 at 445ms p95 latency, outperforming production baseline v2.3.0-prod (nDCG@10=0.8420).',
        'Experiment exp_2026_10_berth_feat achieved nDCG@10 0.8810 hallucination rate 0.0110 445ms p95 latency v2.3.0-prod',
        'demo_ml_model_releases',
        '["ml_eta_predictor_v2_3", "ml_eta_predictor_v2_4_rc1"]'::jsonb,
        '["role:analyst", "role:approver", "role:admin"]'::jsonb,
        'vec_synth_003',
        'en',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

COMMIT;
