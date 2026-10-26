/**
 * Generated & Verified OpenAPI TypeScript Definitions (`apps/web/src/lib/api/schema.d.ts`)
 * Synced with FastAPI `/api/v1/...` schemas (`alba_one.schemas.decision` & `alba_one.api.decisions`).
 * Verified in CI against the backend schema by `apps/api/tests/unit/test_phase8_frontend_contracts.py`.
 */

export type LanguageCode = "ja" | "en";

export type RecommendationVerdict =
  | "recommend_approve"
  | "recommend_approve_with_conditions"
  | "recommend_reject"
  | "needs_more_info";

export type ApprovalAction =
  | "approve"
  | "approve_with_conditions"
  | "reject"
  | "request_more_evidence";

export type DecisionStateType =
  | "draft"
  | "clarifying"
  | "gathering"
  | "hypotheses_ready"
  | "recommended"
  | "awaiting_approval"
  | "approval_recorded_resume_pending"
  | "approved"
  | "approved_with_conditions"
  | "rejected"
  | "needs_evidence"
  | "expired"
  | "cancelled"
  | "outcome_pending"
  | "outcome_reviewed"
  | "closed";

export type CellStatusType =
  | "ok"
  | "parameters_not_verified"
  | "insufficient_data"
  | "missing"
  | "no_evidence";

export interface CriterionSpec {
  id: string;
  name_ja: string;
  name_en: string;
  unit: string;
  direction: "higher_better" | "lower_better" | "n/a";
  kind: "hard_constraint" | "soft_criterion";
  required: boolean;
  source_id: string;
  locator: string;
  hard_limit?: number | null;
  is_regulatory_or_safety?: boolean;
  weight?: number | null;
}

export interface ComparisonCell {
  criterion_id: string;
  status: CellStatusType;
  value: number | string | boolean | null;
  unit: string;
  evidence_id?: string | null;
  hard_constraint_passed?: boolean | null;
}

export interface OptionComparisonRow {
  hypothesis_id: string;
  option_label: string;
  is_baseline: boolean;
  cells: Record<string, ComparisonCell>;
  all_hard_constraints_passed: boolean;
  has_violated_hard_constraint: boolean;
  weighted_total?: number | null;
}

export interface ComparisonTable {
  workflow: string;
  criteria: CriterionSpec[];
  rows: OptionComparisonRow[];
  weights_reviewed_by: string;
  weighted_score_status: "weights_not_reviewed" | "reviewed";
  tradeoffs_summary: string[];
}

export interface ResolvedEvidenceCitation {
  evidence_id: string;
  source_type: string;
  source_id: string;
  url?: string | null;
  retrieved_at: string;
  external: boolean;
  quote?: string | null;
  locator?: string | null;
  resolved_value?: unknown;
}

export interface ValidatedHypothesis {
  hypothesis_id: string;
  option_label: string;
  is_baseline: boolean;
  statement: string;
  stance: "support" | "oppose" | "neutral";
  rationale: string;
  assumptions: string[];
  risks: string[];
  what_would_change_my_mind: string;
  citations: ResolvedEvidenceCitation[];
  acknowledged_gaps: string[];
  depends_on_external: boolean;
  confidence_score: number;
}

export interface JudgeRecommendationOutput {
  recommendation_id: string;
  decision_id: string;
  tenant_id: string;
  workflow: string;
  lang: LanguageCode;
  version: number;
  recommendation_hash: string;
  ledger_snapshot_id: string;
  leading_option_id: string | null;
  proposed_verdict: RecommendationVerdict;
  verdict: RecommendationVerdict;
  gates_applied: string[];
  verdict_overridden_by_rule: string | null;
  options_compared: string[];
  rationale: string;
  conditions: string[];
  risks: string[];
  cited_hypothesis_ids: string[];
  cited_evidence_ids: string[];
  comparison_table: ComparisonTable;
}

export interface TrackedCondition {
  condition_id?: string;
  description: string;
  owner: string;
  due_date: string;
  verification_method: string;
  status?: "open" | "done" | "waived";
  waived_reason?: string | null;
}

export interface DecisionRecord {
  decision_id: string;
  tenant_id: string;
  requester_id: string;
  question: string;
  workflow: string;
  lang: LanguageCode;
  state: DecisionStateType;
  version: number;
  evidence_loops_used: number;
  hypotheses: ValidatedHypothesis[];
  recommendation: JudgeRecommendationOutput;
  tracked_conditions: TrackedCondition[];
  guardrail_blocked_policy?: string | null;
}

export interface ApprovalSubmitPayload {
  action: ApprovalAction;
  rationale?: string;
  conditions?: TrackedCondition[];
  questions?: string[];
  recommendation_id: string;
  recommendation_hash: string;
  expected_version: number;
}

export interface ApprovalSubmitResponse {
  http_status: 202;
  decision_id: string;
  approval_id: string;
  state: DecisionStateType;
  outbox_status: "pending" | "completed" | "failed_retryable";
  diverged_from_recommendation: boolean;
  tracked_conditions: TrackedCondition[];
}

export interface ActualVsPredictedDelta {
  metric_id: string;
  actual_value: number;
  predicted_base: number;
  predicted_low: number;
  predicted_high: number;
  delta_from_base: number;
  pct_delta_from_base: number;
  within_low_high_range: boolean;
  unit: string;
}

export interface ProposedLessonDraft {
  lesson_id: string;
  outcome_id: string;
  decision_id: string;
  tenant_id: string;
  topic_key: string;
  lesson_type:
    | "hypothesis_confirmed"
    | "hypothesis_refuted"
    | "constraint_discovered"
    | "process_improvement";
  statement_ja: string;
  statement_en: string;
  source_acl_tags: string[];
  primary_outcome_label: "confirmed" | "refuted" | "inconclusive";
  reviewer_id: string;
  status: "pending_steward_review" | "active" | "superseded" | "rejected";
  evidence_grade: "single_outcome" | "corroborated";
  corroborated_count: number;
  valid_from: string;
}

export interface OutcomeRecordResponse {
  outcome_id: string;
  decision_id: string;
  tenant_id: string;
  reviewer_id: string;
  actual_kpis: Record<string, number>;
  actual_vs_predicted: ActualVsPredictedDelta[];
  hypothesis_outcomes: Record<string, { label: "confirmed" | "refuted" | "inconclusive"; rationale: string }>;
  conditions_status: TrackedCondition[];
  variance_reason: string;
  proposed_lesson: ProposedLessonDraft;
  reviewed_at: string;
}

export interface StewardWriteBackPayload {
  statement_ja: string;
  statement_en: string;
  approved: boolean;
}

export interface StewardWriteBackResponse {
  status: "written_back" | "rejected";
  lesson: ProposedLessonDraft;
  superseded_lesson_ids: string[];
  kb_chunks_indexed: number;
  memory_id: string;
}

/**
 * Discriminated Union for SSE Decision Events (`schema_version: "1.0"`).
 * Unknown `event_type` values are logged and ignored by `sse.ts`, never crashing the UI.
 */
export type DecisionSSEEvent =
  | {
      schema_version: "1.0";
      event_id: string;
      decision_id: string;
      event_type: "state_changed";
      state: DecisionStateType;
      timestamp: string;
    }
  | {
      schema_version: "1.0";
      event_id: string;
      decision_id: string;
      event_type: "outbox_resumed";
      state: DecisionStateType;
      approval_id: string;
      timestamp: string;
    }
  | {
      schema_version: "1.0";
      event_id: string;
      decision_id: string;
      event_type: "guardrail_alert";
      policy: string;
      action: "block" | "mask";
      timestamp: string;
    };
