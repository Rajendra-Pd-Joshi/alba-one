"use client";

import React, { useState } from "react";
import { MOCK_DECISIONS } from "@/lib/api/mocks";
import type { DecisionRecord, LanguageCode, WorkflowType } from "@/lib/api/schema";
import { ComparisonTable } from "./ComparisonTable";
import { StickyActionBar } from "./StickyActionBar";

interface DecisionWorkspaceProps {
  initialDecision: DecisionRecord;
  lang: LanguageCode;
  canApprove?: boolean;
  onRefresh?: () => Promise<void>;
}

const WORKFLOW_META: Record<WorkflowType, { ja: string; en: string; servers: string[] }> = {
  delivery_planning: {
    ja: "定温配送・ルート計画",
    en: "Cold-Chain Delivery Planning",
    servers: ["delivery_planning", "staffing", "weather_marine", "knowledge_base"],
  },
  vessel_allocation: {
    ja: "船舶バース配船計画",
    en: "Vessel & Berth Allocation",
    servers: ["vessel_allocation", "weather_marine", "sql_readonly", "knowledge_base"],
  },
  staffing: {
    ja: "要員配置・36協定残業管理",
    en: "Staffing & 2024 Overtime Cap",
    servers: ["staffing", "regulatory_jp", "departments", "knowledge_base"],
  },
  model_release: {
    ja: "AIモデル本番昇格審査",
    en: "AI Model Production Release",
    servers: ["experiment_tracking", "benchmark_registry", "deployment_status", "knowledge_base"],
  },
  default: {
    ja: "汎用意思決定",
    en: "General Enterprise Decision",
    servers: ["knowledge_base", "sql_readonly", "decision_history", "memory"],
  },
};

const PIPELINE_STAGES: { id: string; ja: string; en: string; detail: string }[] = [
  { id: "L1", ja: "1. 入力ガードレール", en: "1. Input Guardrail", detail: "PII scrub + Bedrock STANDARD" },
  { id: "CRAG", ja: "2. ハイブリッド検索 (CRAG)", en: "2. Hybrid CRAG Retrieval", detail: "Pinecone + Sudachi FTS + Cohere v4" },
  { id: "CALC", ja: "3. 決定論的ドメイン計算機", en: "3. Deterministic Calculators", detail: "2-Round Shared Evidence Ledger" },
  { id: "HYP", ja: "4. 仮説生成 (H1..Hn + H0)", en: "4. Hypotheses + Baseline H0", detail: "Citation & numeric validator" },
  { id: "JUDGE", ja: "5. 判定上限ゲート (a–g)", en: "5. Judge & Verdict Gates (a–g)", detail: "Deterministic ComparisonTable" },
  { id: "HITL", ja: "6. 人間による最終承認 (HITL)", en: "6. Human Approval (HITL)", detail: "Separation of duties + Outbox" },
];

export function DecisionWorkspace({
  initialDecision,
  lang,
  canApprove = true,
  onRefresh,
}: DecisionWorkspaceProps) {
  const [decision, setDecision] = useState<DecisionRecord>(initialDecision);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>("ev_003");
  const [newQuestion, setNewQuestion] = useState("");
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowType>(initialDecision.workflow);
  const [simulatedRole, setSimulatedRole] = useState<"approver" | "analyst_requester" | "viewer">("approver");
  const [isRunningPipeline, setIsRunningPipeline] = useState(false);

  const rec = decision.recommendation;
  const wasOverridden = Boolean(rec.verdict_overridden_by_rule);
  const wfMeta = WORKFLOW_META[decision.workflow] ?? WORKFLOW_META.default;

  const allCitations = decision.hypotheses.flatMap((h) =>
    h.citations.map((c) => ({ ...c, hypothesisId: h.hypothesis_id, optionLabel: h.option_label }))
  );
  const activeCitation =
    allCitations.find((c) => c.evidence_id === selectedEvidenceId) ?? allCitations[0] ?? null;

  const effectiveCanApprove = canApprove && simulatedRole === "approver";

  const handleRunNewDecision = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newQuestion.trim()) return;
    setIsRunningPipeline(true);
    setTimeout(() => {
      const baseTemplate =
        selectedWorkflow === "model_release"
          ? MOCK_DECISIONS.dec_mock_model_release_en
          : lang === "en"
            ? MOCK_DECISIONS.dec_mock_gates_en
            : MOCK_DECISIONS.dec_mock_gates_ja;
      const customId = `dec_${Date.now().toString().slice(-5)}`;
      setDecision({
        ...baseTemplate,
        decision_id: customId,
        workflow: selectedWorkflow,
        lang,
        question: newQuestion.trim(),
        state: "awaiting_approval",
        version: 1,
      });
      setIsRunningPipeline(false);
    }, 300);
  };

  return (
    <div className="space-y-5 pb-16 text-neutral-text">
      {/* Top 6-Stage Pipeline Telemetry & Active Guardrail Strip */}
      <section
        aria-label={lang === "ja" ? "意思決定パイプライン稼働ステータス" : "Decision Pipeline Execution Telemetry"}
        className="border border-neutral-rule bg-neutral-surface p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-ruleLight pb-3">
          <div className="flex items-center gap-2">
            <span className="border border-secondary-40 px-2 py-0.5 font-mono text-xs font-bold text-secondary-40">
              PIPELINE TRACE
            </span>
            <span className="text-xs font-semibold text-neutral-text">
              {lang === "ja"
                ? `ワークフロー: ${wfMeta.ja}`
                : `Active Workflow: ${wfMeta.en}`}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-neutral-muted [font-variant-numeric:tabular-nums]">
            <span>Guardrails: 7/7 Enforce (STANDARD)</span>
            <span>|</span>
            <span>MCP Servers: {wfMeta.servers.join(", ")}</span>
            <span>|</span>
            <span>Est. Cost: $0.042 (¥6.36)</span>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {PIPELINE_STAGES.map((stg, idx) => {
            const isCurrentHitl = stg.id === "HITL" && decision.state === "awaiting_approval";
            return (
              <div
                key={stg.id}
                className={
                  isCurrentHitl
                    ? "border-2 border-primary-40 bg-neutral-surfaceSubtle p-2.5"
                    : "border border-neutral-ruleLight bg-neutral-surface p-2.5"
                }
              >
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className={isCurrentHitl ? "text-primary-40" : "text-secondary-40"}>
                    {isCurrentHitl ? "● ACTIVE" : `✓ STEP ${idx + 1}`}
                  </span>
                  <span className="font-mono text-neutral-muted">{stg.id}</span>
                </div>
                <div className="mt-1 text-xs font-bold text-neutral-text">
                  {lang === "ja" ? stg.ja : stg.en}
                </div>
                <div className="mt-0.5 text-[11px] text-neutral-muted">{stg.detail}</div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Main 3-Zone Enterprise Grid: Left Queue + Center Workspace + Right Evidence Inspector */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* LEFT SIDEBAR (3 cols): Decision Queue, Role Simulator & New Decision Composer */}
        <aside className="space-y-4 lg:col-span-3">
          <div className="border border-neutral-rule bg-neutral-surface p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-secondary-40">
              {lang === "ja" ? "承認待ち・検証シナリオ一覧" : "Decision Queue & Scenarios"}
            </h2>
            <p className="mt-1 text-xs text-neutral-muted">
              {lang === "ja"
                ? "クリックして各ガバナンス状態（ゲート制限・モデル昇格・ガードレール遮断）を確認できます。"
                : "Select a scenario below to inspect each governance & guardrail state:"}
            </p>
            <div className="mt-3 space-y-2">
              {Object.entries(MOCK_DECISIONS).map(([key, item]) => {
                const isActive = decision.decision_id === item.decision_id;
                const hasGate = item.recommendation.gates_applied.length > 0;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      setDecision(item);
                      const firstEv = item.hypotheses[0]?.citations[0]?.evidence_id ?? null;
                      setSelectedEvidenceId(firstEv);
                    }}
                    className={
                      isActive
                        ? "w-full border-2 border-primary-40 bg-neutral-surfaceSubtle p-3 text-left"
                        : "w-full border border-neutral-ruleLight bg-neutral-surface p-3 text-left hover:border-neutral-rule"
                    }
                  >
                    <div className="flex items-center justify-between gap-1 font-mono text-[11px]">
                      <span className="font-bold text-primary-40">{item.decision_id}</span>
                      <span className="border border-neutral-rule px-1.5 py-0.5 text-neutral-muted">
                        {item.lang.toUpperCase()} | {item.workflow}
                      </span>
                    </div>
                    <div className="mt-1.5 line-clamp-2 text-xs font-semibold text-neutral-text">
                      {item.question}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[11px]">
                      <span className="font-mono text-secondary-40">
                        verdict: {item.recommendation.verdict}
                      </span>
                      {hasGate && (
                        <span className="font-semibold text-quaternary-40">⚠ Gate Active</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* New Decision Query Composer */}
          <form onSubmit={handleRunNewDecision} className="border border-neutral-rule bg-neutral-surface p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-secondary-40">
              {lang === "ja" ? "新規意思決定の起案" : "Draft New Decision"}
            </h2>
            <div className="mt-2.5 space-y-2.5 text-xs">
              <div>
                <label htmlFor="workflow-select" className="block font-semibold text-neutral-text">
                  {lang === "ja" ? "業務ドメイン (Workflow)" : "Domain Workflow"}
                </label>
                <select
                  id="workflow-select"
                  value={selectedWorkflow}
                  onChange={(e) => setSelectedWorkflow(e.target.value as WorkflowType)}
                  className="mt-1 w-full border border-neutral-rule bg-neutral-surface p-2 text-xs text-neutral-text"
                >
                  {(Object.keys(WORKFLOW_META) as WorkflowType[]).map((wf) => (
                    <option key={wf} value={wf}>
                      {WORKFLOW_META[wf][lang]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="new-decision-input" className="block font-semibold text-neutral-text">
                  {lang === "ja" ? "意思決定の問い (Question)" : "Decision Question"}
                </label>
                <textarea
                  id="new-decision-input"
                  rows={3}
                  value={newQuestion}
                  onChange={(e) => setNewQuestion(e.target.value)}
                  placeholder={
                    lang === "ja"
                      ? "例：横浜本牧ふ頭の強風遅延に備え、東京大井B3バースへ優先配船すべきか？"
                      : "e.g., Should we reroute container freight to Tokyo Berth B3?"
                  }
                  className="mt-1 w-full border border-neutral-rule bg-neutral-surface p-2 text-xs text-neutral-text"
                />
              </div>
              <button
                type="submit"
                disabled={isRunningPipeline}
                className="w-full border border-primary-40 bg-primary-40 px-3 py-2 text-xs font-semibold text-neutral-surface"
              >
                {isRunningPipeline
                  ? lang === "ja"
                    ? "パイプライン実行中..."
                    : "Running Pipeline..."
                  : lang === "ja"
                    ? "仮説・比較表を生成"
                    : "Run Decision Pipeline"}
              </button>
            </div>
          </form>

          {/* RBAC & Separation-of-Duties Role Simulator */}
          <div className="border border-neutral-rule bg-neutral-surface p-4 text-xs">
            <h2 className="font-bold uppercase tracking-wider text-secondary-40">
              {lang === "ja" ? "RBAC・職務分掌シミュレータ" : "RBAC & Duty Separation"}
            </h2>
            <p className="mt-1 text-neutral-muted">
              {lang === "ja"
                ? "起案者本人（自己承認禁止）や閲覧者ロールでのボタン制御を検証："
                : "Test separation of duties (requester cannot self-approve):"}
            </p>
            <select
              aria-label="Simulated RBAC Role"
              value={simulatedRole}
              onChange={(e) =>
                setSimulatedRole(e.target.value as "approver" | "analyst_requester" | "viewer")
              }
              className="mt-2 w-full border border-neutral-rule bg-neutral-surface p-2 text-xs font-semibold text-neutral-text"
            >
              <option value="approver">
                {lang === "ja" ? "承認者 (role: approver — 承認可能)" : "Approver (usr_approver_02 — Can Approve)"}
              </option>
              <option value="analyst_requester">
                {lang === "ja"
                  ? "起案者本人 (usr_requester_01 — 自己承認ブロック)"
                  : "Requester (usr_requester_01 — Self-Approval Blocked)"}
              </option>
              <option value="viewer">
                {lang === "ja" ? "閲覧者 (role: viewer — 閲覧専用)" : "Viewer (role: viewer — Read-Only)"}
              </option>
            </select>
          </div>
        </aside>

        {/* CENTER WORKSPACE (6 cols): AI Recommendation + Gates + ComparisonTable + Hypotheses + Action Bar */}
        <div className="space-y-5 lg:col-span-6">
          {/* 1. AI Recommendation Summary */}
          <section
            aria-labelledby="ai-recommendation-heading"
            className="border border-neutral-rule bg-neutral-surface p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="border border-tertiary-40 px-2 py-0.5 text-xs font-bold text-tertiary-40">
                    {lang === "ja" ? "AI推奨 (AI Recommendation)" : "AI recommendation"}
                  </span>
                  <span className="border border-secondary-40 px-2 py-0.5 font-mono text-xs text-secondary-40">
                    workflow: {decision.workflow}
                  </span>
                </div>
                <h2 id="ai-recommendation-heading" className="pt-1 text-lg font-bold text-neutral-text">
                  {decision.question}
                </h2>
              </div>
              <span className="border border-neutral-rule bg-neutral-surfaceSubtle px-2.5 py-1 font-mono text-xs text-neutral-muted">
                state: {decision.state} (v{decision.version})
              </span>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 border-t border-b border-neutral-ruleLight py-3 text-xs sm:grid-cols-3">
              <div>
                <div className="text-neutral-muted">
                  {lang === "ja" ? "ゲート適用後の最終推奨" : "Final clamped verdict"}
                </div>
                <div className="mt-0.5 font-mono text-sm font-bold text-primary-40">{rec.verdict}</div>
              </div>
              {wasOverridden && (
                <>
                  <div>
                    <div className="text-neutral-muted">
                      {lang === "ja" ? "モデル初期出力" : "Original model verdict"}
                    </div>
                    <div className="mt-0.5 font-mono text-sm line-through text-neutral-muted">
                      {rec.proposed_verdict}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-muted">
                      {lang === "ja" ? "適用された上限ルール" : "Overridden by ceiling rule"}
                    </div>
                    <div className="mt-0.5 font-mono text-xs font-semibold text-quaternary-40">
                      {rec.verdict_overridden_by_rule}
                    </div>
                  </div>
                </>
              )}
            </div>

            <p className="mt-3 text-sm leading-relaxed text-neutral-text">{rec.rationale}</p>
          </section>

          {/* 2. Verdict Ceiling Gates Banner */}
          {rec.gates_applied.length > 0 && (
            <section
              aria-labelledby="gates-banner-heading"
              className="border-l-4 border-quaternary-40 bg-neutral-surface p-4"
            >
              <h3 id="gates-banner-heading" className="text-sm font-bold text-quaternary-40">
                ⚠ {lang === "ja" ? "適用された判定上限ルール（Verdict Ceiling Gates）" : "Applied Verdict Ceiling Gates"}
              </h3>
              <ul className="mt-2 space-y-1.5 text-xs">
                {rec.gates_applied.map((ruleId) => {
                  const criterionId = ruleId.includes(":") ? ruleId.split(":")[1] : null;
                  return (
                    <li key={ruleId} className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        <strong className="font-mono">{ruleId}</strong> —{" "}
                        {lang === "ja"
                          ? "未検証の必須制約または不十分な根拠があるため、検証完了まで承認推奨は制限されます。"
                          : "Cannot be recommended for unconditional approval until the required constraint or weight review is completed."}
                      </span>
                      {criterionId && (
                        <a
                          href={`#cell-${criterionId}`}
                          className="border border-secondary-40 px-2 py-0.5 font-medium text-secondary-40 underline"
                        >
                          {lang === "ja" ? `表の該当列（${criterionId}）へ移動` : `Jump to cell (${criterionId})`}
                        </a>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {/* 3. Deterministic Comparison Table */}
          <ComparisonTable
            table={rec.comparison_table}
            lang={lang}
            onSelectEvidence={(evId) => setSelectedEvidenceId(evId)}
          />

          {/* 4. Collapsible Hypotheses & Evidence Ledger */}
          <details className="border border-neutral-rule bg-neutral-surface p-4" open>
            <summary className="cursor-pointer text-sm font-bold text-neutral-text">
              {lang === "ja"
                ? `検証済仮説および必須ベースライン (${decision.hypotheses.length}件 — クリックで開閉)`
                : `Validated Candidate Hypotheses & Mandatory Baseline (${decision.hypotheses.length})`}
            </summary>
            <div className="mt-3 space-y-3">
              {decision.hypotheses.map((h) => (
                <article
                  key={h.hypothesis_id}
                  className={
                    h.is_baseline
                      ? "border border-neutral-rule bg-neutral-surfaceSubtle p-3.5 text-xs"
                      : "border border-neutral-ruleLight bg-neutral-surface p-3.5 text-xs"
                  }
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="border border-secondary-40 px-1.5 py-0.5 font-mono text-[11px] font-bold text-secondary-40">
                        {h.hypothesis_id}
                      </span>
                      <strong className="text-sm text-neutral-text">{h.option_label}</strong>
                    </div>
                    <span className="font-mono text-neutral-muted [font-variant-numeric:tabular-nums]">
                      stance={h.stance} | conf={h.confidence_score.toFixed(2)}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-neutral-text">{h.statement}</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 border-t border-neutral-ruleLight pt-2 text-[11px] sm:grid-cols-2">
                    <div>
                      <span className="font-semibold text-neutral-muted">
                        {lang === "ja" ? "主なリスク: " : "Key Risk: "}
                      </span>
                      <span>{h.risks[0] ?? "—"}</span>
                    </div>
                    <div>
                      <span className="font-semibold text-neutral-muted">
                        {lang === "ja" ? "反証条件: " : "What would change mind: "}
                      </span>
                      <span>{h.what_would_change_my_mind}</span>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {h.citations.map((c) => (
                      <button
                        key={c.evidence_id}
                        type="button"
                        onClick={() => setSelectedEvidenceId(c.evidence_id)}
                        className={
                          selectedEvidenceId === c.evidence_id
                            ? "border border-primary-40 bg-primary-40 px-2 py-0.5 font-mono text-neutral-surface"
                            : "border border-secondary-40 px-2 py-0.5 font-mono text-secondary-40 hover:bg-neutral-surfaceSubtle"
                        }
                      >
                        [{c.evidence_id}: {c.source_id}]
                      </button>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </details>

          {/* 5. Human Decision Action Bar */}
          <StickyActionBar
            decisionId={decision.decision_id}
            recommendation={rec}
            lang={lang}
            canApprove={effectiveCanApprove}
            onRefreshStale={async () => {
              if (onRefresh) await onRefresh();
            }}
            onDecisionRecorded={(newState) =>
              setDecision((prev) => ({ ...prev, state: newState as DecisionRecord["state"] }))
            }
          />
        </div>

        {/* RIGHT INSPECTOR PANEL (3 cols): Live Evidence Ledger, Calculator Provenance & Guardrail Audit */}
        <aside className="space-y-4 lg:col-span-3">
          <div className="border border-neutral-rule bg-neutral-surface p-4 text-xs">
            <div className="flex items-center justify-between border-b border-neutral-ruleLight pb-2.5">
              <h2 className="font-bold uppercase tracking-wider text-secondary-40">
                {lang === "ja" ? "根拠台帳インスペクタ" : "Evidence Ledger Inspector"}
              </h2>
              <span className="font-mono text-[11px] text-neutral-muted">
                snapshot: {rec.ledger_snapshot_id}
              </span>
            </div>

            {activeCitation ? (
              <div className="mt-3 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="border border-secondary-40 px-2 py-0.5 font-mono font-bold text-secondary-40">
                    {activeCitation.evidence_id}
                  </span>
                  <span className="font-mono text-[11px] text-neutral-muted">
                    type: {activeCitation.source_type}
                  </span>
                </div>
                <div>
                  <div className="text-[11px] text-neutral-muted">
                    {lang === "ja" ? "参照元ツール / チャンクID" : "Source Tool / Chunk ID"}
                  </div>
                  <div className="mt-0.5 break-all font-mono font-semibold text-neutral-text">
                    {activeCitation.source_id}
                  </div>
                </div>
                {activeCitation.resolved_value !== undefined && (
                  <div className="border border-neutral-ruleLight bg-neutral-surfaceSubtle p-2.5">
                    <div className="text-[11px] text-neutral-muted">
                      {lang === "ja" ? "決定論的計算機の検証済出力値" : "Verified Deterministic Calculator Value"}
                    </div>
                    <div className="mt-0.5 font-mono text-base font-bold text-primary-40 [font-variant-numeric:tabular-nums]">
                      {String(activeCitation.resolved_value)}
                    </div>
                  </div>
                )}
                {activeCitation.quote && (
                  <div className="border-l-2 border-secondary-40 pl-2.5 italic text-neutral-text">
                    “{activeCitation.quote}”
                  </div>
                )}
                <div className="text-[11px] text-neutral-muted">
                  Retrieved: {activeCitation.retrieved_at} | External: {String(activeCitation.external)}
                </div>
              </div>
            ) : (
              <p className="mt-3 text-neutral-muted">
                {lang === "ja"
                  ? "比較表または仮説カードの [ev_xxx] バッジをクリックすると、ここに根拠の詳細が表示されます。"
                  : "Click any [ev_xxx] badge in the Comparison Table or Hypotheses to inspect its provenance."}
              </p>
            )}

            <div className="mt-4 border-t border-neutral-ruleLight pt-3">
              <div className="text-[11px] font-semibold text-neutral-muted">
                {lang === "ja" ? "この案件の全参照根拠ID:" : "All Cited Evidence IDs in Run:"}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {rec.cited_evidence_ids.map((eid) => (
                  <button
                    key={eid}
                    type="button"
                    onClick={() => setSelectedEvidenceId(eid)}
                    className={
                      selectedEvidenceId === eid
                        ? "border border-primary-40 bg-primary-40 px-2 py-0.5 font-mono text-[11px] text-neutral-surface"
                        : "border border-neutral-rule bg-neutral-surface px-2 py-0.5 font-mono text-[11px] text-neutral-text"
                    }
                  >
                    {eid}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 7-Layer Guardrail & Red-Team Verification Status Card */}
          <div className="border border-neutral-rule bg-neutral-surface p-4 text-xs">
            <h2 className="font-bold uppercase tracking-wider text-secondary-40">
              {lang === "ja" ? "7層ガードレール・監査証跡" : "7-Layer Guardrail & Audit"}
            </h2>
            <ul className="mt-2.5 space-y-2 text-[11px]">
              <li className="flex items-center justify-between border-b border-neutral-ruleLight pb-1.5">
                <span>L1 Input (PII + Bedrock STANDARD)</span>
                <span className="font-mono font-semibold text-secondary-40">✓ PASS</span>
              </li>
              <li className="flex items-center justify-between border-b border-neutral-ruleLight pb-1.5">
                <span>L2 Retriever (ACL + Pinecone Zero-Text)</span>
                <span className="font-mono font-semibold text-secondary-40">✓ PASS</span>
              </li>
              <li className="flex items-center justify-between border-b border-neutral-ruleLight pb-1.5">
                <span>L3 Tool (SQL Views + SSRF + Codenames)</span>
                <span className="font-mono font-semibold text-secondary-40">✓ PASS</span>
              </li>
              <li className="flex items-center justify-between border-b border-neutral-ruleLight pb-1.5">
                <span>L4 Output (Grounding + Beacon Scan)</span>
                <span className="font-mono font-semibold text-secondary-40">✓ PASS</span>
              </li>
              <li className="flex items-center justify-between border-b border-neutral-ruleLight pb-1.5">
                <span>L5 HITL (Separation of Duties)</span>
                <span className="font-mono font-semibold text-primary-40">● AWAITING HUMAN</span>
              </li>
              <li className="flex items-center justify-between">
                <span>Recommendation Hash (409 Guard)</span>
                <span className="font-mono text-neutral-muted">{rec.recommendation_hash}</span>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
