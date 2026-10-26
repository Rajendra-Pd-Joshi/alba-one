import React from "react";
import { TwoStageOutcomeCard } from "@/components/outcomes/TwoStageOutcomeCard";
import { MOCK_OUTCOMES } from "@/lib/api/mocks";
import type { LanguageCode } from "@/lib/api/schema";

interface OutcomesPageProps {
  params: Promise<{ locale: string }>;
}

export default async function OutcomesPage({ params }: OutcomesPageProps) {
  const { locale } = await params;
  const lang: LanguageCode = locale === "en" ? "en" : "ja";
  const sampleOutcome = MOCK_OUTCOMES.out_mock_01;

  return (
    <div className="space-y-4">
      <div className="border-b border-neutral-ruleLight pb-3">
        <span className="text-xs font-semibold text-secondary-40">
          {lang === "ja" ? "結果と知識の運用" : "Outcome and knowledge operations"}
        </span>
        <h1 className="font-display text-2xl font-bold text-neutral-text">
          {lang === "ja" ? "成果レビューおよび教訓の書き戻し" : "Outcome Review & Knowledge Steward Write-Back"}
        </h1>
      </div>
      <TwoStageOutcomeCard
        outcome={sampleOutcome}
        lang={lang}
        currentUserId="usr_steward_99"
        currentUserName="Knowledge Steward Sato"
        currentUserRole="knowledge_steward"
        writebackRequiresDifferentPerson={true}
      />
    </div>
  );
}
