"use client";

import React, { useState } from "react";
import { APIRequestError, submitApprovalDecision } from "@/lib/api/api";
import type {
  ApprovalAction,
  JudgeRecommendationOutput,
  LanguageCode,
  TrackedCondition,
} from "@/lib/api/schema";

interface StickyActionBarProps {
  decisionId: string;
  recommendation: JudgeRecommendationOutput;
  lang: LanguageCode;
  canApprove: boolean;
  onRefreshStale: () => Promise<void>;
  onDecisionRecorded: (newState: string) => void;
}

const VERDICT_RANK: Record<string, number> = {
  needs_more_info: 0,
  recommend_reject: 1,
  recommend_approve_with_conditions: 2,
  recommend_approve: 3,
};

const ACTION_PERMISSIVENESS: Record<ApprovalAction, number> = {
  request_more_evidence: 0,
  reject: 1,
  approve_with_conditions: 2,
  approve: 3,
};

export function StickyActionBar({
  decisionId,
  recommendation,
  lang,
  canApprove,
  onRefreshStale,
  onDecisionRecorded,
}: StickyActionBarProps) {
  const [selectedAction, setSelectedAction] = useState<ApprovalAction | null>(null);
  const [rationale, setRationale] = useState("");
  const [conditions, setConditions] = useState<TrackedCondition[]>([
    { description: "", owner: "", due_date: "2026-10-31", verification_method: "" },
  ]);
  const [questionText, setQuestionText] = useState("");
  const [staleBanner, setStaleBanner] = useState<string | null>(null);
  const [statusAnnouncement, setStatusAnnouncement] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => `idem_${Date.now()}`);

  const isDivergingFromCeiling =
    selectedAction !== null &&
    ACTION_PERMISSIVENESS[selectedAction] > (VERDICT_RANK[recommendation.verdict] ?? 0);

  const rationaleRequired =
    selectedAction === "reject" ||
    selectedAction === "request_more_evidence" ||
    selectedAction === "approve_with_conditions" ||
    isDivergingFromCeiling;

  const handleSelectAction = (action: ApprovalAction) => {
    setSelectedAction(action);
    setErrorBanner(null);
    setIdempotencyKey(`idem_${decisionId}_${action}_${Date.now()}`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAction) return;

    if (rationaleRequired && !rationale.trim()) {
      setErrorBanner(
        lang === "ja"
          ? "判断理由（rationale）の入力が必須です。"
          : "Rationale is mandatory for the selected action."
      );
      return;
    }

    try {
      const res = await submitApprovalDecision(
        decisionId,
        {
          action: selectedAction,
          rationale: rationale.trim() || undefined,
          conditions:
            selectedAction === "approve_with_conditions"
              ? conditions.filter((c) => c.description.trim())
              : undefined,
          questions:
            selectedAction === "request_more_evidence"
              ? questionText
                  .split("\n")
                  .map((q) => q.trim())
                  .filter(Boolean)
              : undefined,
          recommendation_id: recommendation.recommendation_id,
          recommendation_hash: recommendation.recommendation_hash,
          expected_version: recommendation.version,
        },
        idempotencyKey
      );
      setStaleBanner(null);
      setStatusAnnouncement(
        lang === "ja"
          ? `承認を記録しました（状態: ${res.state} / 再開処理中）`
          : `Approval recorded, resuming (${res.state})`
      );
      onDecisionRecorded(res.state);
    } catch (err) {
      if (err instanceof APIRequestError && err.status === 409) {
        // Preserve typed rationale and conditions while refreshing recommendation!
        setStaleBanner(
          lang === "ja"
            ? "推奨内容が更新されました。入力済みの判断理由を保持したまま最新状態を再取得しました。"
            : "The recommendation has changed. View refreshed while preserving your typed rationale."
        );
        await onRefreshStale();
      } else if (err instanceof APIRequestError) {
        setErrorBanner(lang === "ja" ? err.messageJa : err.messageEn);
      } else {
        setErrorBanner(String(err));
      }
    }
  };

  return (
    <footer
      aria-label={lang === "ja" ? "承認の判断（人間による最終決定）" : "Decision (Human Action Bar)"}
      className="sticky bottom-0 z-20 max-h-[45vh] overflow-y-auto border-t-2 border-primary-40 bg-neutral-surface p-4 shadow-sm pb-[max(1rem,env(safe-area-inset-bottom))]"
    >
      <div aria-live="polite" className="sr-only">
        {statusAnnouncement ?? staleBanner ?? errorBanner ?? ""}
      </div>

      {staleBanner && (
        <div role="alert" className="mb-3 border border-quaternary-40 p-3 text-xs font-semibold text-quaternary-40">
          ⚠ {staleBanner}
        </div>
      )}
      {statusAnnouncement && (
        <div role="status" className="mb-3 border border-secondary-40 p-3 text-xs font-semibold text-secondary-40">
          ✓ {statusAnnouncement}
        </div>
      )}
      {errorBanner && (
        <div role="alert" className="mb-3 border border-quaternary-40 p-3 text-xs font-semibold text-quaternary-40">
          ✕ {errorBanner}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-bold text-neutral-text">
          {lang === "ja" ? "承認の判断" : "Decision"}
        </div>

        {!canApprove ? (
          <p role="note" className="text-xs text-neutral-muted">
            {lang === "ja"
              ? "閲覧専用：現在のロールにはこのワークフローの承認権限がありません。"
              : "Read-only: Your current role is not authorized to approve this workflow."}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => handleSelectAction("approve")}
              className="border border-primary-40 bg-primary-40 px-3.5 py-2 text-xs font-semibold text-neutral-surface"
            >
              {lang === "ja" ? "承認" : "Approve"}
            </button>
            <button
              type="button"
              onClick={() => handleSelectAction("approve_with_conditions")}
              className="border border-secondary-40 bg-neutral-surface px-3.5 py-2 text-xs font-semibold text-secondary-40"
            >
              {lang === "ja" ? "条件付き承認" : "Approve with conditions"}
            </button>
            <button
              type="button"
              onClick={() => handleSelectAction("reject")}
              className="border border-quaternary-40 bg-neutral-surface px-3.5 py-2 text-xs font-semibold text-quaternary-40"
            >
              {lang === "ja" ? "却下" : "Reject"}
            </button>
            <button
              type="button"
              onClick={() => handleSelectAction("request_more_evidence")}
              className="border border-neutral-rule bg-neutral-surface px-3.5 py-2 text-xs font-semibold text-neutral-text"
            >
              {lang === "ja" ? "追加根拠を依頼" : "Request more evidence"}
            </button>
          </div>
        )}
      </div>

      {canApprove && selectedAction && (
        <form
          role="dialog"
          aria-modal="false"
          aria-labelledby="decision-action-dialog-title"
          onSubmit={handleSubmit}
          className="mt-4 space-y-3 border border-neutral-rule bg-neutral-surfaceSubtle p-4"
        >
          <h4 id="decision-action-dialog-title" className="text-sm font-bold text-neutral-text">
            {isDivergingFromCeiling
              ? lang === "ja"
                ? `AI推奨上限（${recommendation.verdict}）を超える判断の確認`
                : `Confirm Action More Permissive Than Ceiling (${recommendation.verdict})`
              : `${lang === "ja" ? "選択アクション" : "Selected Action"}: ${selectedAction}`}
          </h4>

          {isDivergingFromCeiling && (
            <p className="border-l-2 border-quaternary-40 pl-2 text-xs text-quaternary-40">
              {lang === "ja"
                ? `適用ゲート [${recommendation.gates_applied.join(", ")}] によりAI推奨は ${recommendation.verdict} に制限されています。人間による上位判断（diverged_from_recommendation=true）として記録するため、理由を記入してください。`
                : `Gates [${recommendation.gates_applied.join(", ")}] capped the AI recommendation at ${recommendation.verdict}. Enter a mandatory rationale to record diverged_from_recommendation=true.`}
            </p>
          )}

          <div>
            <label htmlFor="hitl-rationale-input" className="block text-xs font-semibold text-neutral-text">
              {lang === "ja" ? "判断理由（必須）" : "Rationale (mandatory)"}
            </label>
            <textarea
              id="hitl-rationale-input"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={2}
              required={rationaleRequired}
              className="mt-1 w-full border border-neutral-rule bg-neutral-surface p-2 text-xs text-neutral-text"
            />
          </div>

          {selectedAction === "approve_with_conditions" && (
            <div className="space-y-2">
              <div className="text-xs font-semibold text-neutral-text">
                {lang === "ja" ? "付帯条件（内容・責任者・期限・検証方法）" : "Structured Conditions"}
              </div>
              {conditions.map((cond, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                  <input
                    type="text"
                    placeholder={lang === "ja" ? "条件内容" : "Description"}
                    value={cond.description}
                    onChange={(e) => {
                      const next = [...conditions];
                      next[idx] = { ...next[idx], description: e.target.value };
                      setConditions(next);
                    }}
                    className="border border-neutral-rule bg-neutral-surface p-1.5 text-xs"
                  />
                  <input
                    type="text"
                    placeholder={lang === "ja" ? "責任者ロール" : "Owner"}
                    value={cond.owner}
                    onChange={(e) => {
                      const next = [...conditions];
                      next[idx] = { ...next[idx], owner: e.target.value };
                      setConditions(next);
                    }}
                    className="border border-neutral-rule bg-neutral-surface p-1.5 text-xs"
                  />
                  <input
                    type="date"
                    value={cond.due_date}
                    onChange={(e) => {
                      const next = [...conditions];
                      next[idx] = { ...next[idx], due_date: e.target.value };
                      setConditions(next);
                    }}
                    className="border border-neutral-rule bg-neutral-surface p-1.5 text-xs"
                  />
                  <input
                    type="text"
                    placeholder={lang === "ja" ? "検証方法" : "Verification method"}
                    value={cond.verification_method}
                    onChange={(e) => {
                      const next = [...conditions];
                      next[idx] = { ...next[idx], verification_method: e.target.value };
                      setConditions(next);
                    }}
                    className="border border-neutral-rule bg-neutral-surface p-1.5 text-xs"
                  />
                </div>
              ))}
            </div>
          )}

          {selectedAction === "request_more_evidence" && (
            <div>
              <label htmlFor="hitl-questions-input" className="block text-xs font-semibold text-neutral-text">
                {lang === "ja" ? "追加収集する質問（1行1項目）" : "Questions to gather (one per line)"}
              </label>
              <textarea
                id="hitl-questions-input"
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                rows={2}
                required
                className="mt-1 w-full border border-neutral-rule bg-neutral-surface p-2 text-xs"
              />
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              className="border border-primary-40 bg-primary-40 px-4 py-1.5 text-xs font-semibold text-neutral-surface"
            >
              {lang === "ja" ? "判断を確定して送信" : "Confirm & Submit Decision"}
            </button>
            <button
              type="button"
              onClick={() => setSelectedAction(null)}
              className="border border-neutral-rule bg-neutral-surface px-3 py-1.5 text-xs text-neutral-muted"
            >
              {lang === "ja" ? "キャンセル" : "Cancel"}
            </button>
          </div>
        </form>
      )}
    </footer>
  );
}
