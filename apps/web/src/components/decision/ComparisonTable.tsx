import React from "react";
import type { ComparisonCell, ComparisonTable as ComparisonTableType, LanguageCode } from "@/lib/api/schema";

interface ComparisonTableProps {
  table: ComparisonTableType;
  lang: LanguageCode;
  onSelectEvidence: (evidenceId: string) => void;
}

const STATUS_BADGE_LABELS: Record<string, { ja: string; en: string; icon: string; isAlert: boolean }> = {
  parameters_not_verified: {
    ja: "パラメータ未検証",
    en: "Parameters not verified",
    icon: "⚠",
    isAlert: true,
  },
  insufficient_data: {
    ja: "データ不足",
    en: "Insufficient data",
    icon: "!",
    isAlert: true,
  },
  missing: {
    ja: "データ欠損",
    en: "Missing",
    icon: "—",
    isAlert: false,
  },
  no_evidence: {
    ja: "根拠なし",
    en: "No evidence",
    icon: "?",
    isAlert: false,
  },
};

function renderCellBadge(cell: ComparisonCell, lang: LanguageCode) {
  if (cell.status !== "ok") {
    const meta = STATUS_BADGE_LABELS[cell.status] ?? STATUS_BADGE_LABELS.missing;
    const text = lang === "ja" ? meta.ja : meta.en;
    const borderClass = meta.isAlert
      ? "border-quaternary-40 text-quaternary-40"
      : "border-neutral-rule text-neutral-muted";
    return (
      <span
        role="status"
        aria-label={`${meta.icon} ${text} (${cell.status})`}
        title={`${text} (${cell.status})`}
        className={`inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-medium ${borderClass}`}
      >
        <span aria-hidden="true">{meta.icon}</span>
        <span>{text}</span>
      </span>
    );
  }

  if (cell.hard_constraint_passed === false) {
    const label = lang === "ja" ? "必須制約違反" : "Hard constraint violated";
    return (
      <span
        role="status"
        aria-label={`✕ ${label}`}
        className="inline-flex items-center gap-1 border border-quaternary-40 px-2 py-0.5 text-xs font-semibold text-quaternary-40"
      >
        <span aria-hidden="true">✕</span>
        <span>{label}</span>
      </span>
    );
  }

  if (cell.hard_constraint_passed === true) {
    // Brand has no green: use Secondary (#006685) + checkmark icon + text label
    const label = lang === "ja" ? "必須制約充足" : "Constraint satisfied";
    return (
      <span
        role="status"
        aria-label={`✓ ${label}`}
        className="inline-flex items-center gap-1 border border-secondary-40 px-2 py-0.5 text-xs font-medium text-secondary-40"
      >
        <span aria-hidden="true">✓</span>
        <span>{label}</span>
      </span>
    );
  }
  return null;
}

export function ComparisonTable({ table, lang, onSelectEvidence }: ComparisonTableProps) {
  const showWeights = table.weighted_score_status === "reviewed";

  return (
    <section aria-labelledby="comparison-table-heading" className="border border-neutral-ruleLight bg-neutral-surface p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 id="comparison-table-heading" className="text-base font-bold text-neutral-text">
          {lang === "ja" ? "選択肢・評価基準の決定論的比較表" : "Deterministic Option Comparison Table"}
        </h3>
        {!showWeights && (
          <span
            role="note"
            aria-label={
              lang === "ja"
                ? "重み付け未承認（総合スコア非表示）"
                : "Weights not reviewed (composite score hidden)"
            }
            className="inline-flex items-center gap-1 border border-neutral-rule bg-neutral-surfaceSubtle px-2.5 py-1 text-xs text-neutral-muted"
          >
            <span aria-hidden="true">ℹ</span>
            <span>
              {lang === "ja"
                ? "重み付け未承認（総合スコア非表示：weights_not_reviewed）"
                : "Weights not reviewed (composite score hidden: weights_not_reviewed)"}
            </span>
          </span>
        )}
      </div>

      {/* Desktop / Tablet Horizontally Scrollable Table with Sticky First Column */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm [font-variant-numeric:tabular-nums]">
          <thead>
            <tr className="border-b border-neutral-rule bg-neutral-surfaceSubtle">
              <th scope="col" className="sticky left-0 z-10 bg-neutral-surfaceSubtle p-3 font-semibold text-neutral-text">
                {lang === "ja" ? "選択肢（仮説）" : "Option (Hypothesis)"}
              </th>
              {table.criteria.map((c) => (
                <th key={c.id} id={`cell-${c.id}`} scope="col" className="p-3 font-semibold text-neutral-text">
                  <div>{lang === "ja" ? c.name_ja : c.name_en}</div>
                  <div className="text-xs font-normal text-neutral-muted">
                    {c.kind === "hard_constraint"
                      ? lang === "ja"
                        ? `[必須制約 / ${c.unit}]`
                        : `[Hard constraint / ${c.unit}]`
                      : `[${c.unit}]`}
                  </div>
                </th>
              ))}
              {showWeights && (
                <th scope="col" className="p-3 font-semibold text-neutral-text">
                  {lang === "ja" ? "重み付き総合値" : "Weighted Total"}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr key={row.hypothesis_id} className="border-b border-neutral-ruleLight">
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-neutral-surface p-3 font-semibold text-neutral-text"
                >
                  <div>{row.option_label}</div>
                  {row.is_baseline && (
                    <span className="mt-1 inline-block border border-neutral-rule px-1.5 py-0.5 text-xs font-normal text-neutral-muted">
                      {lang === "ja" ? "必須ベースライン仮説" : "Mandatory Baseline"}
                    </span>
                  )}
                </th>
                {table.criteria.map((c) => {
                  const cell = row.cells[c.id];
                  return (
                    <td key={c.id} className="p-3 align-top">
                      {cell.status === "ok" && cell.value !== null && (
                        <div className="font-mono text-sm font-semibold text-neutral-text [font-variant-numeric:tabular-nums]">
                          {String(cell.value)} <span className="text-xs font-normal text-neutral-muted">{cell.unit}</span>
                        </div>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {renderCellBadge(cell, lang)}
                        {cell.evidence_id && (
                          <button
                            type="button"
                            onClick={() => onSelectEvidence(cell.evidence_id!)}
                            aria-label={`${lang === "ja" ? "根拠を参照" : "View evidence"} ${cell.evidence_id}`}
                            className="border border-secondary-40 px-1.5 py-0.5 text-xs font-medium text-secondary-40 hover:bg-neutral-surfaceSubtle"
                          >
                            [{cell.evidence_id}]
                          </button>
                        )}
                      </div>
                    </td>
                  );
                })}
                {showWeights && (
                  <td className="p-3 font-mono [font-variant-numeric:tabular-nums]">
                    {row.weighted_total ?? "—"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Narrow Screen Per-Option Card View */}
      <div className="space-y-3 md:hidden">
        {table.rows.map((row) => (
          <div key={row.hypothesis_id} className="border border-neutral-rule p-3 [font-variant-numeric:tabular-nums]">
            <div className="font-bold text-neutral-text">{row.option_label}</div>
            <dl className="mt-2 space-y-2 text-xs">
              {table.criteria.map((c) => {
                const cell = row.cells[c.id];
                return (
                  <div key={c.id} className="flex flex-col border-t border-neutral-ruleLight pt-1.5">
                    <dt className="font-medium text-neutral-muted">{lang === "ja" ? c.name_ja : c.name_en}</dt>
                    <dd className="mt-1 flex items-center justify-between gap-2">
                      <span>{cell.status === "ok" && cell.value !== null ? `${cell.value} ${cell.unit}` : ""}</span>
                      {renderCellBadge(cell, lang)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
