import type { Config } from "tailwindcss";

/**
 * ALBA ONE — Strict ALBACONNECT Brand Theme (`apps/web/tailwind.config.ts`)
 * Source: https://albaconnect.co.jp/about/brand
 *
 * Binding rules (Phase 8 User Answer 0):
 * - Fonts: Zen Kaku Gothic New (Japanese), Manrope (Latin/numerals), Inter Tight (large English headings).
 * - Colours:
 *   - Primary:    40 = #0052FF (primary actions)
 *   - Secondary:  40 = #006685 (evidence, citations, structure)
 *   - Tertiary:   40 = #8424DA (AI-generated items accent)
 *   - Quaternary: 40 = #B6250A (alerts, blocks, warnings)
 *   - Neutral:    text #1B1B1B to #5E5E5E, rules #C6C6C6 / #E2E2E2, surfaces #FFFFFF / #F7F7F7
 * - Light theme only. No gradients, no heavy shadows, no green.
 */
export const ALBA_BRAND_COLORS = {
  primary: {
    40: "#0052FF",
    DEFAULT: "#0052FF",
  },
  secondary: {
    40: "#006685",
    DEFAULT: "#006685",
  },
  tertiary: {
    40: "#8424DA",
    DEFAULT: "#8424DA",
  },
  quaternary: {
    40: "#B6250A",
    DEFAULT: "#B6250A",
  },
  neutral: {
    text: "#1B1B1B",
    muted: "#5E5E5E",
    rule: "#C6C6C6",
    ruleLight: "#E2E2E2",
    surface: "#FFFFFF",
    surfaceSubtle: "#F7F7F7",
  },
} as const;

export const ALBA_BRAND_FONTS = {
  ja: ["Zen Kaku Gothic New", "sans-serif"],
  sans: ["Manrope", "Zen Kaku Gothic New", "sans-serif"],
  display: ["Inter Tight", "Manrope", "Zen Kaku Gothic New", "sans-serif"],
} as const;

const config: Config = {
  darkMode: ["class", "[data-theme='never-dark']"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    colors: ALBA_BRAND_COLORS,
    fontFamily: ALBA_BRAND_FONTS,
    extend: {
      boxShadow: {
        none: "none",
        hairline: "0 1px 0 0 #E2E2E2",
      },
    },
  },
  plugins: [],
};

export default config;
