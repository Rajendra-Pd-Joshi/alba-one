import React from "react";
import { Inter_Tight, Manrope, Zen_Kaku_Gothic_New } from "next/font/google";
import "../globals.css";
import { isExplicitMockMode } from "@/lib/api/api";
import type { LanguageCode } from "@/lib/api/schema";

const zenKaku = Zen_Kaku_Gothic_New({
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  preload: false,
  variable: "--font-zen-kaku",
});

const manrope = Manrope({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-manrope",
});

const interTight = Inter_Tight({
  weight: ["600", "700"],
  subsets: ["latin"],
  variable: "--font-inter-tight",
});

interface LocaleLayoutProps {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}

/**
 * Root Locale Layout (`apps/web/src/app/[locale]/layout.tsx`)
 * Matches the exact header, typography, and footer of https://albaconnect.co.jp/en/service/alba-one
 * and https://albaconnect.co.jp/service/alba-one.
 */
export default async function LocaleLayout({ children, params }: LocaleLayoutProps) {
  const { locale } = await params;
  const lang: LanguageCode = locale === "en" ? "en" : "ja";
  const mocked = isExplicitMockMode();

  return (
    <html
      lang={lang}
      data-mocked={mocked ? "true" : "false"}
      className={`${zenKaku.variable} ${manrope.variable} ${interTight.variable}`}
    >
      <body className="min-h-screen bg-neutral-surface font-sans text-neutral-text antialiased">
        {mocked && (
          <div
            role="status"
            data-testid="mock-data-banner"
            className="border-b border-neutral-ruleLight bg-neutral-surfaceSubtle px-4 py-1 text-center text-[11px] font-medium text-neutral-muted"
          >
            デモデータ / Demo data (NEXT_PUBLIC_USE_MOCKS=true)
          </div>
        )}

        {/* Official ALBACONNECT Top Navigation Bar */}
        <header className="sticky top-0 z-30 border-b border-neutral-ruleLight bg-neutral-surface">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:px-10">
            <a href={`/${lang}`} className="flex items-center gap-3">
              <img
                src="/brand/albaconnect-logo.svg"
                alt="ALBACONNECT — ALBA ONE"
                width={148}
                height={30}
              />
            </a>

            <nav aria-label="Main navigation" className="hidden items-center gap-8 text-sm font-medium md:flex">
              <a href={`/${lang}#our-service`} className="text-neutral-text hover:text-primary-40">
                {lang === "ja" ? "事業・サービス" : "Services"}
              </a>
              <a href={`/${lang}#point-of-view`} className="text-neutral-text hover:text-primary-40">
                {lang === "ja" ? "私たちについて" : "About"}
              </a>
              <a href={`/${lang}#workspace`} className="font-semibold text-primary-40">
                {lang === "ja" ? "意思決定ワークスペース" : "Decision Workspace"}
              </a>
              <a href={`/${lang}/outcomes`} className="text-neutral-text hover:text-primary-40">
                {lang === "ja" ? "最新の知見・成果レビュー" : "Insights & Outcomes"}
              </a>
            </nav>

            <div className="flex items-center gap-5">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                <a
                  href="/en"
                  className={lang === "en" ? "font-bold text-primary-40 underline" : "text-neutral-muted hover:text-neutral-text"}
                >
                  EN
                </a>
                <span className="text-neutral-rule">/</span>
                <a
                  href="/ja"
                  className={lang === "ja" ? "font-bold text-primary-40 underline" : "text-neutral-muted hover:text-neutral-text"}
                >
                  JP
                </a>
              </div>
              <a
                href={`/${lang}#workspace`}
                className="border border-primary-40 bg-primary-40 px-4 py-2 text-xs font-semibold text-neutral-surface hover:opacity-95"
              >
                {lang === "ja" ? "お問い合わせ" : "Contact"}
              </a>
            </div>
          </div>
        </header>

        <main>{children}</main>

        {/* Official ALBACONNECT Footer (`albaconnect.co.jp/en/service/alba-one`) */}
        <footer className="border-t border-neutral-rule bg-neutral-surface text-neutral-text">
          {/* Let's talk CTA Band */}
          <div className="border-b border-neutral-ruleLight bg-neutral-surfaceSubtle px-6 py-14 lg:px-10">
            <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 md:flex-row md:items-center">
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-widest text-secondary-40">
                  {lang === "ja" ? "お問い合わせ" : "Contact"}
                </div>
                <h2 className="font-display text-3xl font-bold tracking-tight text-neutral-text">
                  Let&apos;s talk.
                </h2>
                <p className="max-w-2xl text-sm text-neutral-muted">
                  {lang === "ja"
                    ? "事業成長につながる、AI・システム活用をご支援します。「何を作るべきか」という構想整理から、設計・開発・運用まで。事業・業務・データを踏まえた実践的な支援を行います。"
                    : "We support AI and system adoption that drives business growth. From clarifying \"what to build\" to design, development, and operations. Practical support grounded in your business, operations, and data."}
                </p>
              </div>
              <a
                href={`/${lang}#workspace`}
                className="border border-primary-40 bg-primary-40 px-6 py-3 text-sm font-semibold text-neutral-surface"
              >
                {lang === "ja" ? "お問い合わせ" : "Contact Us"}
              </a>
            </div>
          </div>

          {/* Footer Links & ISMS / Toranomon Hills Address */}
          <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10">
            <div className="grid grid-cols-1 gap-8 border-b border-neutral-ruleLight pb-10 md:grid-cols-5">
              <div className="space-y-3 md:col-span-2">
                <img
                  src="/brand/albaconnect-logo.svg"
                  alt="ALBACONNECT"
                  width={140}
                  height={28}
                />
                <p className="text-xs leading-relaxed text-neutral-muted">
                  {lang === "ja"
                    ? "〒105-6416 東京都港区虎ノ門1-17-1 虎ノ門ヒルズビジネスタワー16階"
                    : "Toranomon Hills Business Tower 16F, 1-17-1 Toranomon, Minato-ku, Tokyo 105-6416"}
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-1 font-mono text-[11px] text-secondary-40">
                  <span className="border border-secondary-40 px-2 py-0.5">MSA-IS-861</span>
                  <span className="border border-secondary-40 px-2 py-0.5">ISMS ISR016 (ISO/IEC 27001)</span>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div className="font-bold text-neutral-text">
                  {lang === "ja" ? "事業・サービス" : "Services"}
                </div>
                <ul className="space-y-1.5 text-neutral-muted">
                  <li><a href={`/${lang}#our-service`} className="hover:text-primary-40">{lang === "ja" ? "事業・サービス一覧" : "All services"}</a></li>
                  <li><a href={`/${lang}#intended-outcomes`} className="hover:text-primary-40">{lang === "ja" ? "業務課題別ソリューション" : "Practice solutions"}</a></li>
                  <li><a href={`/${lang}#workspace`} className="hover:text-primary-40">{lang === "ja" ? "プロダクト (ALBA ONE)" : "Products (ALBA ONE)"}</a></li>
                </ul>
              </div>

              <div className="space-y-2 text-xs">
                <div className="font-bold text-neutral-text">
                  {lang === "ja" ? "私たちについて" : "Company"}
                </div>
                <ul className="space-y-1.5 text-neutral-muted">
                  <li><a href={`/${lang}#point-of-view`} className="hover:text-primary-40">{lang === "ja" ? "私たちについて" : "About"}</a></li>
                  <li><a href={`/${lang}#measuring-value`} className="hover:text-primary-40">{lang === "ja" ? "目指す未来" : "Vision"}</a></li>
                  <li><a href="https://albaconnect.co.jp/about/brand" target="_blank" rel="noreferrer" className="hover:text-primary-40">{lang === "ja" ? "ブランドガイドライン" : "Brand Guidelines"}</a></li>
                </ul>
              </div>

              <div className="space-y-2 text-xs">
                <div className="font-bold text-neutral-text">
                  {lang === "ja" ? "知見・運用" : "Journal & Ops"}
                </div>
                <ul className="space-y-1.5 text-neutral-muted">
                  <li><a href={`/${lang}/outcomes`} className="hover:text-primary-40">{lang === "ja" ? "成果レビュー・知識還元" : "Outcome & Steward Ops"}</a></li>
                  <li><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-primary-40">OpenAPI (/docs)</a></li>
                </ul>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 text-xs text-neutral-muted">
              <div className="flex flex-wrap gap-4">
                <span>{lang === "ja" ? "プライバシーポリシー" : "Privacy Policy"}</span>
                <span>{lang === "ja" ? "情報セキュリティ基本方針" : "Information Security Policy"}</span>
                <span>{lang === "ja" ? "サイトマップ" : "Sitemap"}</span>
              </div>
              <div>© 2026 ALBACONNECT Inc. All rights reserved.</div>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
