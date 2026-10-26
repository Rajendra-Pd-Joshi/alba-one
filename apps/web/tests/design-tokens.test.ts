import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ALBA_BRAND_COLORS, ALBA_BRAND_FONTS } from "../tailwind.config";
import { assertProductionBuildRejectsMocks } from "../next.config.mjs";
import { computeDiffSegments } from "../src/lib/diff";
import { parseAndValidateSSEFrame } from "../src/lib/api/sse";

const ALLOWED_HEX_SET = new Set([
  "#0052FF",
  "#006685",
  "#8424DA",
  "#B6250A",
  "#1B1B1B",
  "#5E5E5E",
  "#C6C6C6",
  "#E2E2E2",
  "#FFFFFF",
  "#F7F7F7",
]);

const EXPECTED_LOGO_SHA256 = "5e77186d156577cc589b350f9d1f17a0e58df92596268f14cf83267695223e52";

describe("ALBACONNECT Brand Tokens & Phase 8 Contracts", () => {
  it("asserts exact ALBACONNECT hex colours and rejects any non-brand colour", () => {
    expect(ALBA_BRAND_COLORS.primary[40]).toBe("#0052FF");
    expect(ALBA_BRAND_COLORS.secondary[40]).toBe("#006685");
    expect(ALBA_BRAND_COLORS.tertiary[40]).toBe("#8424DA");
    expect(ALBA_BRAND_COLORS.quaternary[40]).toBe("#B6250A");
    expect(ALBA_BRAND_COLORS.neutral.text).toBe("#1B1B1B");
    expect(ALBA_BRAND_COLORS.neutral.muted).toBe("#5E5E5E");
    expect(ALBA_BRAND_COLORS.neutral.rule).toBe("#C6C6C6");
    expect(ALBA_BRAND_COLORS.neutral.ruleLight).toBe("#E2E2E2");

    // Collect every hex string in ALBA_BRAND_COLORS and fail if any unapproved colour (e.g. green) appears
    const collectHex = (obj: unknown): string[] => {
      if (typeof obj === "string") return [obj.toUpperCase()];
      if (obj && typeof obj === "object") {
        return Object.values(obj).flatMap(collectHex);
      }
      return [];
    };
    for (const hex of collectHex(ALBA_BRAND_COLORS)) {
      expect(ALLOWED_HEX_SET.has(hex)).toBe(true);
    }
  });

  it("asserts exact ALBACONNECT font families", () => {
    expect(ALBA_BRAND_FONTS.ja[0]).toBe("Zen Kaku Gothic New");
    expect(ALBA_BRAND_FONTS.sans[0]).toBe("Manrope");
    expect(ALBA_BRAND_FONTS.display[0]).toBe("Inter Tight");
  });

  it("verifies committed ALBACONNECT logo SVG hash is unmodified", () => {
    const svgPath = path.resolve(__dirname, "../public/brand/albaconnect-logo.svg");
    const bytes = fs.readFileSync(svgPath);
    const sha = crypto.createHash("sha256").update(bytes).digest("hex");
    expect(sha).toBe(EXPECTED_LOGO_SHA256);
  });

  it("fails production build when NEXT_PUBLIC_USE_MOCKS=true", () => {
    expect(() =>
      assertProductionBuildRejectsMocks({
        NODE_ENV: "production",
        NEXT_PUBLIC_USE_MOCKS: "true",
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow(/NEXT_PUBLIC_USE_MOCKS=true is forbidden/);
  });

  it("computes character-level diff for Japanese and word-level diff for English", () => {
    const jaSegs = computeDiffSegments("東京港B3着岸", "東京港B4優先着岸", "ja");
    expect(jaSegs.some((s) => s.type === "removed" && s.text === "3")).toBe(true);
    expect(jaSegs.some((s) => s.type === "added" && s.text === "4優先")).toBe(true);

    const enSegs = computeDiffSegments("berth B3 ready", "berth B4 ready", "en");
    expect(enSegs.some((s) => s.type === "removed" && s.text === "B3")).toBe(true);
    expect(enSegs.some((s) => s.type === "added" && s.text === "B4")).toBe(true);
  });

  it("deduplicates SSE events by event_id and ignores unknown event types without crashing", () => {
    const seen = new Set<string>();
    const validRaw = JSON.stringify({
      schema_version: "1.0",
      event_id: "ev_sse_1",
      decision_id: "dec_1",
      event_type: "state_changed",
      state: "approved",
      timestamp: "2026-10-24T00:00:00Z",
    });
    expect(parseAndValidateSSEFrame(validRaw, seen)).not.toBeNull();
    expect(parseAndValidateSSEFrame(validRaw, seen)).toBeNull(); // duplicate ignored

    const unknownRaw = JSON.stringify({
      schema_version: "1.0",
      event_id: "ev_sse_2",
      decision_id: "dec_1",
      event_type: "future_unknown_type",
    });
    expect(parseAndValidateSSEFrame(unknownRaw, seen)).toBeNull();
  });
});
