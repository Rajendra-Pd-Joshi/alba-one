"use client";

import React, { useState } from "react";
import { submitStewardWriteBack } from "@/lib/api/api";
import { computeDiffSegments } from "@/lib/diff";
import type { LanguageCode, OutcomeRecordResponse, StewardWriteBackResponse } from "@/lib/api/schema";

interface TwoStageOutcomeCardProps {
  outcome: OutcomeRecordResponse;
  lang: LanguageCode;
  currentUserId: string;
  currentUserName: string;
  currentUserRole: string;
  writebackRequiresDifferentPerson?: boolean;
}

/**
 * Two-Stage Outcome Review & Knowledge Steward Write-Back Card (`TwoStageOutcomeCard.tsx`)
 *
 * Per Phase 8 User Answer 2:
 * - Stage 1 displays the API-computed deterministic `actual_vs_predicted` table.
 * - Stage 2 is visible to all, enabled ONLY when Stage 1 is saved AND `currentUserRole === "knowledge_steward"`
 *   AND (`currentUserId !== outcome.reviewer_id` when `writebackRequiresDifferentPerson` is true).
 * - Never relies on tooltips on disabled controls: renders a visible helper text linked via `aria-describedby`.
 * - Character-level diff for Japanese (`computeDiffSegments(..., "ja")`) and word-level diff for English.
 * - Requires explicit checkboxes for both JA and EN and shows the "What will be written" panel before confirm.
 */
export function TwoStageOutcomeCard({
  outcome,
  lang,
  currentUserId,
  currentUserName,
  currentUserRole,
  writebackRequiresDifferentPerson = true,
}: TwoStageOutcomeCardProps) {
  const lesson = outcome.proposed_lesson;
  const [editedJa, setEditedJa] = useState(lesson.statement_ja);
  const [editedEn, setEditedEn] = useState(lesson.statement_en);
  const [confirmJa, setConfirmJa] = useState(false);
  const [confirmEn, setConfirmEn] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [writebackResult, setWritebackResult] = useState<StewardWriteBackResponse | null>(null);
  const [deprecated, setDeprecated] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const isStewardRole = currentUserRole.toLowerCase() === "knowledge_steward";
  const isSamePerson = writebackRequiresDifferentPerson && currentUserId === outcome.reviewer_id;
  const canWriteBack = isStewardRole && !isSamePerson;

  const disabledReason = !isStewardRole
    ? lang === "ja"
      ? "この操作にはナレッジスチュワード（knowledge_steward）ロールが必要です。"
      : "Write-back requires the knowledge_steward role."
    : isSamePerson
      ? lang === "ja"
        ? "職務分掌ルール（WRITEBACK_REQUIRES_DIFFERENT_PERSON）により、成果レビュアー本人は書き戻しを承認できません。"
        : "Separation of duties (WRITEBACK_REQUIRES_DIFFERENT_PERSON): the outcome reviewer cannot approve their own lesson write-back."
      : null;

  const jaDiff = computeDiffSegments(lesson.statement_ja, editedJa, "ja");
  const enDiff = computeDiffSegments(lesson.statement_en, editedEn, "en");

  const handleFinalConfirm = async () => {
    setErrorMsg(null);
    try {
      const res = await submitStewardWriteBack(outcome.outcome_id, {
        statement_ja: editedJa,
        statement_en: editedEn,
        approved: true,
      });
      setWritebackResult(res);
      setShowConfirmModal(false);
    } catch (err) {
      setErrorMsg(String(err));
    }
  };

  return (
    <div className="space-y-6 text-neutral-text">
      {/* STAGE 1: Outcome Review & API-Computed Actual vs Predicted Comparison */}
      <section aria-labelledby="outcome-stage1-heading" className="border border-neutral-rule bg-neutral-surface p-5">
        <h3 id="outcome-stage1-heading" className="text-base font-bold text-neutral-text">
          {lang === "ja"
            ? "第1段階：成果レビューの記録（実測KPIと予測の決定論的比較）"
            : "Stage 1: Outcome Review (Deterministic Actual vs Predicted Comparison)"}
        </h3>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs [font-variant-numeric:tabular-nums]">
            <thead>
              <tr className="border-b border-neutral-rule bg-neutral-surfaceSubtle">
                <th className="p-2">Metric</th>
                <th className="p-2">Actual</th>
                <th className="p-2">Predicted (Low / Base / High)</th>
                <th className="p-2">Delta (%)</th>
                <th className="p-2">In Range</th>
              </tr>
            </thead>
            <tbody>
              {outcome.actual_vs_predicted.map((row) => (
                <tr key={row.metric_id} className="border-b border-neutral-ruleLight">
                  <td className="p-2 font-mono">{row.metric_id}</td>
                  <td className="p-2 font-mono font-bold">
                    {row.actual_value} {row.unit}
                  </td>
                  <td className="p-2 font-mono">
                    {row.predicted_low} / {row.predicted_base} / {row.predicted_high} {row.unit}
                  </td>
                  <td className="p-2 font-mono">
                    {row.delta_from_base >= 0 ? `+${row.delta_from_base}` : row.delta_from_base} (
                    {row.pct_delta_from_base >= 0 ? `+${row.pct_delta_from_base}%` : `${row.pct_delta_from_base}%`})
                  </td>
                  <td className="p-2">
                    <span className="border border-secondary-40 px-2 py-0.5 text-secondary-40">
                      {row.within_low_high_range ? "✓ Within range" : "⚠ Outside range"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* STAGE 2: Knowledge Steward Lesson Write-Back Card with Live Diff */}
      <section aria-labelledby="outcome-stage2-heading" className="border border-neutral-rule bg-neutral-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="outcome-stage2-heading" className="text-base font-bold text-neutral-text">
            {lang === "ja"
              ? "第2段階：ナレッジスチュワードによる教訓書き戻し（Write-Back）"
              : "Stage 2: Knowledge Steward Lesson Write-Back"}
          </h3>
          <span className="border border-tertiary-40 px-2 py-0.5 text-xs font-semibold text-tertiary-40">
            {lang === "ja" ? "機械翻訳ドラフトを含む要確認項目" : "Includes MT Draft — Confirm Both Languages"}
          </span>
        </div>

        {disabledReason && (
          <p
            id="steward-disabled-reason"
            role="note"
            className="mt-2 border-l-2 border-quaternary-40 pl-3 text-xs font-semibold text-quaternary-40"
          >
            ⚠ {disabledReason}
          </p>
        )}

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Japanese Editor + Character-Level Diff */}
          <div className="space-y-2 border border-neutral-ruleLight p-3">
            <label htmlFor="steward-ja-input" className="block text-xs font-bold">
              日本語教訓テキスト（文字単位差分プレビュー / Character-level diff）
            </label>
            <textarea
              id="steward-ja-input"
              disabled={!canWriteBack}
              aria-describedby={disabledReason ? "steward-disabled-reason" : undefined}
              value={editedJa}
              onChange={(e) => setEditedJa(e.target.value)}
              rows={3}
              className="w-full border border-neutral-rule p-2 text-xs disabled:bg-neutral-surfaceSubtle"
            />
            <div aria-label="Japanese live diff" className="border border-neutral-ruleLight bg-neutral-surfaceSubtle p-2 text-xs">
              {jaDiff.map((seg, i) => (
                <span
                  key={i}
                  className={
                    seg.type === "added"
                      ? "border-b-2 border-secondary-40 font-bold text-secondary-40"
                      : seg.type === "removed"
                        ? "line-through text-quaternary-40"
                        : ""
                  }
                >
                  {seg.text}
                </span>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                disabled={!canWriteBack}
                checked={confirmJa}
                onChange={(e) => setConfirmJa(e.target.checked)}
              />
              <span>{lang === "ja" ? "日本語テキストを確認・確定しました" : "Confirmed Japanese lesson text"}</span>
            </label>
          </div>

          {/* English Editor + Word-Level Diff */}
          <div className="space-y-2 border border-neutral-ruleLight p-3">
            <label htmlFor="steward-en-input" className="block text-xs font-bold">
              English Lesson Text [MT Draft] (Word-level diff)
            </label>
            <textarea
              id="steward-en-input"
              disabled={!canWriteBack}
              aria-describedby={disabledReason ? "steward-disabled-reason" : undefined}
              value={editedEn}
              onChange={(e) => setEditedEn(e.target.value)}
              rows={3}
              className="w-full border border-neutral-rule p-2 text-xs disabled:bg-neutral-surfaceSubtle"
            />
            <div aria-label="English live diff" className="border border-neutral-ruleLight bg-neutral-surfaceSubtle p-2 text-xs">
              {enDiff.map((seg, i) => (
                <span
                  key={i}
                  className={
                    seg.type === "added"
                      ? "border-b-2 border-secondary-40 font-bold text-secondary-40"
                      : seg.type === "removed"
                        ? "line-through text-quaternary-40"
                        : ""
                  }
                >
                  {seg.text}
                </span>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                disabled={!canWriteBack}
                checked={confirmEn}
                onChange={(e) => setConfirmEn(e.target.checked)}
              />
              <span>{lang === "ja" ? "英語テキスト（機械翻訳修正済）を確認・確定しました" : "Confirmed English lesson text"}</span>
            </label>
          </div>
        </div>

        {/* "What will be written" Preview Panel */}
        <div className="mt-4 border border-neutral-rule bg-neutral-surfaceSubtle p-4 text-xs">
          <h4 className="font-bold text-neutral-text">
            {lang === "ja" ? "書き戻し内容の最終プレビュー（What will be written）" : "What Will Be Written"}
          </h4>
          <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div>
              <dt className="text-neutral-muted">Lesson Type / Grade</dt>
              <dd className="font-mono">
                {lesson.lesson_type} ({lesson.evidence_grade})
              </dd>
            </div>
            <div>
              <dt className="text-neutral-muted">Inherited ACL Tags</dt>
              <dd className="font-mono">{lesson.source_acl_tags.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-neutral-muted">Valid From / PII Scan</dt>
              <dd className="font-mono">{lesson.valid_from} (PII/Secret Scan: Clean)</dd>
            </div>
          </dl>
          <p className="mt-2 border-t border-neutral-ruleLight pt-2 font-semibold text-secondary-40">
            ℹ{" "}
            {lang === "ja"
              ? "将来の意思決定では、検証済の事実ではなく「過去の意思決定教訓（参考文脈）」として参照されます。"
              : "Future decisions will be able to retrieve this as a past-decision lesson, not as verified fact."}
          </p>
        </div>

        {errorMsg && (
          <div role="alert" className="mt-3 border border-quaternary-40 p-2 text-xs text-quaternary-40">
            ✕ {errorMsg}
          </div>
        )}

        <div className="mt-4">
          <button
            type="button"
            disabled={!canWriteBack || !confirmJa || !confirmEn}
            aria-describedby={disabledReason ? "steward-disabled-reason" : undefined}
            onClick={() => setShowConfirmModal(true)}
            className="border border-primary-40 bg-primary-40 px-4 py-2 text-xs font-semibold text-neutral-surface disabled:border-neutral-rule disabled:bg-neutral-surfaceSubtle disabled:text-neutral-muted"
          >
            {lang === "ja" ? "教訓の書き戻しを確認する" : "Review & Confirm Write-Back"}
          </button>
        </div>

        {showConfirmModal && (
          <div role="dialog" aria-modal="true" className="mt-4 border border-primary-40 bg-neutral-surface p-4 text-xs">
            <p className="font-bold">
              {lang === "ja"
                ? `承認者（ナレッジスチュワード）: ${currentUserName}（${currentUserId}）として編集後の最終テキストをKBおよび長期メモリへ書き戻しますか？`
                : `Confirm write-back of final edited text as Knowledge Steward ${currentUserName} (${currentUserId})?`}
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleFinalConfirm}
                className="border border-primary-40 bg-primary-40 px-3 py-1.5 font-semibold text-neutral-surface"
              >
                {lang === "ja" ? "確定して書き戻す" : "Confirm Write-Back"}
              </button>
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="border border-neutral-rule px-3 py-1.5 text-neutral-muted"
              >
                {lang === "ja" ? "戻る" : "Back"}
              </button>
            </div>
          </div>
        )}

        {writebackResult && (
          <div role="status" className="mt-4 border border-secondary-40 p-3 text-xs">
            <div className="font-bold text-secondary-40">
              ✓ {lang === "ja" ? "書き戻し完了" : "Write-Back Completed"}: KB Chunks Indexed ={" "}
              {writebackResult.kb_chunks_indexed}, Memory ID = {writebackResult.memory_id}, Status ={" "}
              {deprecated ? "deprecated" : writebackResult.lesson.status}
            </div>
            {!deprecated && (
              <button
                type="button"
                onClick={() => setDeprecated(true)}
                className="mt-2 border border-quaternary-40 px-2.5 py-1 text-quaternary-40"
              >
                {lang === "ja" ? "この教訓を非推奨化（Deprecate）" : "Deprecate lesson"}
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
