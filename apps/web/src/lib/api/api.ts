/**
 * Typed API Client (`apps/web/src/lib/api/api.ts`)
 *
 * Per Phase 8 User Answer 3:
 * - Wraps `fetch` using `/api/proxy/v1/...` (Next.js cookie-forwarding proxy route).
 * - Mocks are EXPLICIT (`process.env.NEXT_PUBLIC_USE_MOCKS === "true"`), NEVER a fallback.
 * - Any network or HTTP error against the real backend throws `APIRequestError` so the UI
 *   renders a proper bilingual error state and NEVER silently switches to mock data.
 */

import { MOCK_DECISIONS, MOCK_OUTCOMES } from "./mocks";
import type {
  ApprovalSubmitPayload,
  ApprovalSubmitResponse,
  DecisionRecord,
  OutcomeRecordResponse,
  StewardWriteBackPayload,
  StewardWriteBackResponse,
} from "./schema";

export class APIRequestError extends Error {
  public readonly status: number;
  public readonly messageJa: string;
  public readonly messageEn: string;

  constructor(status: number, messageJa: string, messageEn: string) {
    super(`[HTTP ${status}] ${messageJa} / ${messageEn}`);
    this.status = status;
    this.messageJa = messageJa;
    this.messageEn = messageEn;
  }
}

export function isExplicitMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "true";
}

export async function fetchDecision(decisionId: string): Promise<DecisionRecord> {
  if (isExplicitMockMode()) {
    const found = MOCK_DECISIONS[decisionId] ?? MOCK_DECISIONS.dec_mock_gates_ja;
    return structuredClone(found);
  }

  const res = await fetch(`/api/proxy/v1/decisions/${encodeURIComponent(decisionId)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new APIRequestError(
      res.status,
      body?.detail?.message_ja ?? "意思決定データの取得に失敗しました。",
      body?.detail?.message_en ?? "Failed to fetch decision record."
    );
  }
  return (await res.json()) as DecisionRecord;
}

export async function submitApprovalDecision(
  decisionId: string,
  payload: ApprovalSubmitPayload,
  idempotencyKey: string,
  options?: { simulateStale409?: boolean }
): Promise<ApprovalSubmitResponse> {
  if (isExplicitMockMode()) {
    if (options?.simulateStale409) {
      throw new APIRequestError(
        409,
        "表示以降に推奨内容またはエビデンスが更新されています。",
        "Recommendation hash or version changed since display; refresh before deciding."
      );
    }
    return {
      http_status: 202,
      decision_id: decisionId,
      approval_id: `apr_mock_${Date.now()}`,
      state: "approval_recorded_resume_pending",
      outbox_status: "pending",
      diverged_from_recommendation: payload.action === "approve",
      tracked_conditions: payload.conditions ?? [],
    };
  }

  const res = await fetch(`/api/proxy/v1/approvals/${encodeURIComponent(decisionId)}/decide`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new APIRequestError(
      res.status,
      body?.detail?.message_ja ?? "承認送信エラーが発生しました。",
      body?.detail?.message_en ?? "Failed to submit approval decision."
    );
  }
  return (await res.json()) as ApprovalSubmitResponse;
}

export async function fetchOutcomeRecord(outcomeId: string): Promise<OutcomeRecordResponse> {
  if (isExplicitMockMode()) {
    return structuredClone(MOCK_OUTCOMES[outcomeId] ?? MOCK_OUTCOMES.out_mock_01);
  }
  const res = await fetch(`/api/proxy/v1/outcomes/${encodeURIComponent(outcomeId)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new APIRequestError(res.status, "成果レビューの取得に失敗しました。", "Failed to fetch outcome review.");
  }
  return (await res.json()) as OutcomeRecordResponse;
}

export async function submitStewardWriteBack(
  outcomeId: string,
  payload: StewardWriteBackPayload
): Promise<StewardWriteBackResponse> {
  if (isExplicitMockMode()) {
    const base = structuredClone(MOCK_OUTCOMES.out_mock_01.proposed_lesson);
    base.statement_ja = payload.statement_ja;
    base.statement_en = payload.statement_en;
    base.status = payload.approved ? "active" : "rejected";
    return {
      status: payload.approved ? "written_back" : "rejected",
      lesson: base,
      superseded_lesson_ids: [],
      kb_chunks_indexed: payload.approved ? 2 : 0,
      memory_id: "mem_mock_wb_01",
    };
  }

  const res = await fetch(`/api/proxy/v1/outcomes/${encodeURIComponent(outcomeId)}/write-back`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new APIRequestError(
      res.status,
      body?.detail ?? "教訓の書き戻し権限エラー（403）",
      body?.detail ?? "Steward write-back forbidden (403)"
    );
  }
  return (await res.json()) as StewardWriteBackResponse;
}
