import React from "react";
import { DecisionWorkspace } from "@/components/decision/DecisionWorkspace";
import { MOCK_DECISIONS } from "@/lib/api/mocks";
import type { LanguageCode } from "@/lib/api/schema";

interface WorkspacePageProps {
  params: Promise<{ locale: string }>;
}

/**
 * Official ALBA ONE Service & Interactive Decision OS Page (`apps/web/src/app/[locale]/page.tsx`)
 * Strictly follows the exact layout, typography, numbered sections (`01 Point of View`,
 * `02 Our Service`, `03 Intended Outcomes`, `04 Measuring Value`), and Connected Capabilities
 * of https://albaconnect.co.jp/en/service/alba-one and https://albaconnect.co.jp/service/alba-one,
 * with the live interactive ALBA ONE Decision Workspace embedded seamlessly.
 */
export default async function WorkspacePage({ params }: WorkspacePageProps) {
  const { locale } = await params;
  const lang: LanguageCode = locale === "en" ? "en" : "ja";
  const initialDecision =
    lang === "en" ? MOCK_DECISIONS.dec_mock_gates_en : MOCK_DECISIONS.dec_mock_gates_ja;

  const serviceDomains =
    lang === "ja"
      ? [
          {
            num: "01",
            title: "知識基盤とオントロジー統合 (Knowledge & Data Foundations)",
            desc: "社内に散在するデータベース（読み取り専用ビュー）、規定文書、過去の判断履歴をPIIマスキングと権限タグ（ACL）付きで統合し、検索・検証可能な知識資産へ変換します。",
          },
          {
            num: "02",
            title: "決定論的計算機と仮説比較 (Deterministic Option Comparison)",
            desc: "配車・バース配船・要員残業上限（36協定）・モデル昇格などの制約条件を計算機で厳密に評価し、現状維持（必須ベースライン仮説 H0）を含む複数の選択肢を根拠と共に比較します。",
          },
          {
            num: "03",
            title: "判定上限ゲート・人間承認・成果還元 (Verdict Gates, HITL & Outcomes)",
            desc: "未検証の必須制約がある場合はAI推奨を自動制限（Verdict Ceiling Gates）し、職務分掌に基づく人間承認（HITL）と実行後の予測対実績レビューを通じて組織の判断力を継続的に高めます。",
          },
        ]
      : [
          {
            num: "01",
            title: "Knowledge foundations and ontology integration",
            desc: "Connect on-premise databases (read-only views), operational rules, and past decision records with PII scrubbing and permission tags (ACLs) into a reviewable knowledge foundation.",
          },
          {
            num: "02",
            title: "Deterministic calculators and hypothesis comparison",
            desc: "Evaluate dispatch, berth allocation, Article 36 overtime caps, and release SLOs in deterministic code, comparing candidate options against a mandatory status-quo baseline (H0).",
          },
          {
            num: "03",
            title: "Verdict ceiling gates, human approval and outcome loops",
            desc: "Enforce deterministic verdict ceiling rules (a–g), separation-of-duties human sign-off (HITL), and two-stage steward outcome reviews so every decision compounds into a company asset.",
          },
        ];

  const intendedOutcomes =
    lang === "ja"
      ? [
          {
            num: "01",
            title: "AI推奨と人間の最終決定の明確な分離",
            desc: "AIは根拠付きの推奨（Recommendation）と制約チェックを担い、最終決定（Decision）は権限を持つ人間が行うことで、説明責任と統制を維持します。",
          },
          {
            num: "02",
            title: "根拠と前提条件が揃った選択肢比較",
            desc: "定温SLA超過確率、コスト、労務上限、リスクを一覧表で揃え、なぜその選択肢を優先すべきかを誰でも検証できる状態をつくります。",
          },
          {
            num: "03",
            title: "結果から学び続ける意思決定資産",
            desc: "判断時の予測値と実行後の実績値を照合し、ナレッジスチュワードの承認を経て教訓を知識ベースへ還元します。",
          },
        ]
      : [
          {
            num: "01",
            title: "Clear boundary between AI recommendation and human decision",
            desc: "Make clear where AI proposes evidence-backed recommendations and where accountable people decide, preserving auditability and separation of duties.",
          },
          {
            num: "02",
            title: "Options teams can compare with verifiable evidence",
            desc: "Align SLA breach probability, route economics, regulatory caps, and risks in a single deterministic table so teams can inspect both the numbers and the process.",
          },
          {
            num: "03",
            title: "Decision rationale and outcomes that remain as assets",
            desc: "Connect predicted KPIs with actual post-execution outcomes and steward-reviewed lessons so organizational judgment improves with every run.",
          },
        ];

  const measuringValue =
    lang === "ja"
      ? [
          {
            num: "01",
            title: "業務速度・リードタイム指標",
            desc: "判断に必要な根拠収集・選択肢比較・承認リードタイムと手直し工数",
          },
          {
            num: "02",
            title: "判断品質・監査トレーサビリティ指標",
            desc: "必須制約（36協定・SLA・セキュリティ）の事前検証率と根拠引用の完全性",
          },
          {
            num: "03",
            title: "事業成果・ROA貢献指標",
            desc: "配車・配船・投資判断における予測対実績の乖離縮小と資産稼働効率",
          },
        ]
      : [
          {
            num: "01",
            title: "Operational velocity",
            desc: "Time required to gather evidence, compare options, and complete review handoffs.",
          },
          {
            num: "02",
            title: "Decision & audit quality",
            desc: "Pre-execution constraint verification rate, citation completeness, and reduction in rework.",
          },
          {
            num: "03",
            title: "Enterprise ROA & value",
            desc: "Calibration between predicted and actual KPIs across fleet, staffing, and model assets.",
          },
        ];

  return (
    <div className="bg-neutral-surface text-neutral-text">
      {/* 1. Hero Section (Exact match to albaconnect.co.jp/en/service/alba-one) */}
      <section className="border-b border-neutral-ruleLight px-6 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="text-xs font-bold uppercase tracking-widest text-secondary-40">
            {lang === "ja" ? "プロダクト / 意思決定OS" : "Products / Decision OS"}
          </div>
          <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-neutral-text sm:text-5xl">
            ALBA ONE
          </h1>
          <p className="mt-4 max-w-3xl font-display text-xl font-semibold text-neutral-text sm:text-2xl">
            {lang === "ja"
              ? "何を優先し、どの条件で、どう判断するか。"
              : "What to prioritise, under which conditions, and why."}
          </p>
          <p className="mt-4 max-w-3xl text-base leading-relaxed text-neutral-muted">
            {lang === "ja"
              ? "業務知識とデータ、判断基準と結果をつなぎ、企業の判断を資産にする、意思決定OS（Decision OS）の構築・運用プラットフォームです。"
              : "A Decision OS platform connecting operational knowledge, data, decision criteria and outcomes to build decisions into compounding company assets."}
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <a
              href="#workspace"
              className="border border-primary-40 bg-primary-40 px-6 py-3 text-sm font-semibold text-neutral-surface"
            >
              {lang === "ja" ? "意思決定ワークスペースを試す" : "Launch Decision Workspace"}
            </a>
            <a
              href={`/${lang}/outcomes`}
              className="border border-neutral-rule bg-neutral-surface px-6 py-3 text-sm font-semibold text-neutral-text hover:border-primary-40"
            >
              {lang === "ja" ? "成果レビュー・知識還元を見る" : "Explore Outcome & Steward Ops"}
            </a>
          </div>
        </div>
      </section>

      {/* 2. Sticky Section Index Bar (`01 Point of View | 02 Our Service | 03 Intended Outcomes | 04 Measuring Value`) */}
      <nav
        aria-label="Page sections"
        className="border-b border-neutral-ruleLight bg-neutral-surfaceSubtle px-6 py-3.5 lg:px-10"
      >
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-6 text-xs font-semibold sm:gap-10">
          <a href="#point-of-view" className="flex items-center gap-2 text-neutral-text hover:text-primary-40">
            <span className="font-mono text-secondary-40">01</span>
            <span>{lang === "ja" ? "基本的な考え方 (Point of View)" : "Point of View"}</span>
          </a>
          <a href="#our-service" className="flex items-center gap-2 text-neutral-text hover:text-primary-40">
            <span className="font-mono text-secondary-40">02</span>
            <span>{lang === "ja" ? "提供機能 (Our Service)" : "Our Service"}</span>
          </a>
          <a href="#workspace" className="flex items-center gap-2 font-bold text-primary-40">
            <span className="font-mono">LIVE</span>
            <span>{lang === "ja" ? "意思決定ワークスペース (Workspace)" : "Interactive Decision Workspace"}</span>
          </a>
          <a href="#intended-outcomes" className="flex items-center gap-2 text-neutral-text hover:text-primary-40">
            <span className="font-mono text-secondary-40">03</span>
            <span>{lang === "ja" ? "もたらす変化 (Intended Outcomes)" : "Intended Outcomes"}</span>
          </a>
          <a href="#measuring-value" className="flex items-center gap-2 text-neutral-text hover:text-primary-40">
            <span className="font-mono text-secondary-40">04</span>
            <span>{lang === "ja" ? "価値の測り方 (Measuring Value)" : "Measuring Value"}</span>
          </a>
        </div>
      </nav>

      {/* 3. Section 01: Point of View & Asset Leverage Thesis */}
      <section id="point-of-view" className="border-b border-neutral-ruleLight px-6 py-16 lg:px-10">
        <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <div className="font-mono text-xs font-bold uppercase tracking-widest text-secondary-40">
              01 / Point of View
            </div>
            <h2 className="mt-2 font-display text-2xl font-bold text-neutral-text sm:text-3xl">
              {lang === "ja"
                ? "企業の判断を、再現可能な資産に変える。"
                : "Turn enterprise judgment into a reviewable, compounding asset."}
            </h2>
          </div>
          <div className="space-y-6 lg:col-span-8">
            <p className="text-base leading-relaxed text-neutral-text">
              {lang === "ja"
                ? "配車やバース配船、要員配置、AIモデルの本番昇格など、現場と経営の重要な判断は、納期・設備制約・労務規定・コストといった複数の条件が絡み合います。ALBA ONEは、属人化した判断基準と社内データを結び、選択肢の比較から承認、結果の振り返りまでを一貫して支えます。"
                : "Critical operational and management decisions—across cold-chain dispatch, berth allocation, workforce staffing, and model governance—depend on delivery commitments, regulatory constraints, and asset economics. ALBA ONE makes these conditions explicit so teams can compare options, verify evidence, and retain the rationale behind every decision."}
            </p>
            <div className="border-l-2 border-secondary-40 bg-neutral-surfaceSubtle p-5">
              <div className="text-xs font-bold uppercase tracking-wider text-secondary-40">
                {lang === "ja" ? "資産活用の考え方 (Asset Leverage Thesis)" : "Asset leverage thesis"}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-neutral-text">
                {lang === "ja"
                  ? "ROA（総資産利益率）を最大化するという目的を、人・設備・車両・知識データの具体的な使い方へ分解する。前提条件と不確実性を明らかにし、AIの推論と決定論的計算機、そして人間の判断（HITL）を適切に分担させます。"
                  : "Translate the aim of maximising ROA into concrete use of people, vessels, vehicles, and data. Combine deterministic domain calculators with governed AI synthesis and human-in-the-loop (HITL) sign-off so every decision builds institutional capability."}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Section 02: Our Service (01 / 02 / 03 Grid) */}
      <section id="our-service" className="border-b border-neutral-ruleLight bg-neutral-surfaceSubtle px-6 py-16 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="font-mono text-xs font-bold uppercase tracking-widest text-secondary-40">
            02 / Our Service
          </div>
          <h2 className="mt-2 font-display text-2xl font-bold text-neutral-text sm:text-3xl">
            {lang === "ja"
              ? "ALBA ONE（意思決定OS）を構成する3つのコア領域"
              : "Core capabilities tailored to ALBA ONE Decision OS."}
          </h2>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
            {serviceDomains.map((item) => (
              <div key={item.num} className="border border-neutral-rule bg-neutral-surface p-6">
                <div className="font-mono text-sm font-bold text-primary-40">{item.num}</div>
                <h3 className="mt-3 text-base font-bold text-neutral-text">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-muted">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. LIVE INTERACTIVE DECISION WORKSPACE */}
      <section id="workspace" className="border-b border-neutral-rule px-6 py-14 lg:px-10">
        <div className="mx-auto max-w-7xl space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-rule pb-4">
            <div>
              <span className="font-mono text-xs font-bold uppercase tracking-widest text-primary-40">
                {lang === "ja" ? "ライブ実行環境 / Interactive Platform" : "Live Interactive Platform"}
              </span>
              <h2 className="mt-1 font-display text-2xl font-bold text-neutral-text sm:text-3xl">
                {lang === "ja" ? "意思決定ワークスペース" : "Decision Workspace"}
              </h2>
            </div>
            <p className="max-w-xl text-xs text-neutral-muted">
              {lang === "ja"
                ? "7層ガードレール・22種のMCPツール・決定論的比較表・判定上限ルール（a〜g）・人間による最終承認（HITL）をその場で操作・検証できます。"
                : "Inspect the live 6-stage pipeline, deterministic option comparison table, verdict ceiling gates (a–g), evidence ledger provenance, and human approval bar below."}
            </p>
          </div>

          <DecisionWorkspace initialDecision={initialDecision} lang={lang} canApprove={true} />
        </div>
      </section>

      {/* 6. Section 03: Intended Outcomes */}
      <section id="intended-outcomes" className="border-b border-neutral-ruleLight px-6 py-16 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="font-mono text-xs font-bold uppercase tracking-widest text-secondary-40">
            03 / Intended Outcomes
          </div>
          <h2 className="mt-2 font-display text-2xl font-bold text-neutral-text sm:text-3xl">
            {lang === "ja" ? "この変革がもたらす3つの構造的変化" : "What this transformation changes."}
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-neutral-muted">
            {lang === "ja"
              ? "単発のAIツール導入で終わらせず、現場の意思決定速度・業務品質・組織全体のROA向上へ直結する仕組みを実装します。"
              : "We design every deployment so daily operational improvements translate directly into auditable governance and compounding enterprise value."}
          </p>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
            {intendedOutcomes.map((item) => (
              <div key={item.num} className="border-t-2 border-neutral-text pt-4">
                <div className="font-mono text-xs font-bold text-secondary-40">{item.num}</div>
                <h3 className="mt-2 text-base font-bold text-neutral-text">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-muted">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 7. Section 04: Measuring Value */}
      <section id="measuring-value" className="bg-neutral-surfaceSubtle px-6 py-16 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="font-mono text-xs font-bold uppercase tracking-widest text-secondary-40">
            04 / Measuring Value
          </div>
          <h2 className="mt-2 font-display text-2xl font-bold text-neutral-text sm:text-3xl">
            {lang === "ja" ? "進捗と成果を測る指標" : "Agree on what progress means."}
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-neutral-muted">
            {lang === "ja"
              ? "現状のベースライン、評価期間、対象ワークフローの指標を合意した上で運用を開始します。"
              : "We agree on the current baseline, evaluation period and measures for your workflow. These are discussion points, rather than promised results."}
          </p>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
            {measuringValue.map((item) => (
              <div key={item.num} className="border border-neutral-rule bg-neutral-surface p-6">
                <div className="font-mono text-xs font-bold text-primary-40">{item.num}</div>
                <h3 className="mt-2 text-base font-bold text-neutral-text">{item.title}</h3>
                <p className="mt-2 text-sm text-neutral-muted">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
