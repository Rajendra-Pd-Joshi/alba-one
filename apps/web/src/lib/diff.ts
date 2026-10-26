/**
 * Bilingual Diff Engine (`apps/web/src/lib/diff.ts`)
 *
 * Per Phase 8 User Answer 2:
 * - Japanese (`lang === "ja"`) has no word spaces, so we compute a CHARACTER-LEVEL
 *   Longest Common Subsequence (LCS) diff (`Array.from(text)`).
 * - English (`lang === "en"`) uses a WORD-LEVEL LCS diff (`text.split(/(\s+)/)`).
 * - Zero external dependencies; deterministic and unit-tested in `design-tokens.test.ts`
 *   and `test_phase8_frontend_contracts.py`.
 */

export interface DiffSegment {
  type: "unchanged" | "added" | "removed";
  text: string;
}

function tokenizeForLocale(text: string, lang: "ja" | "en"): string[] {
  if (lang === "ja") {
    return Array.from(text);
  }
  return text.split(/(\s+)/).filter((t) => t.length > 0);
}

export function computeDiffSegments(
  draftText: string,
  editedText: string,
  lang: "ja" | "en"
): DiffSegment[] {
  const a = tokenizeForLocale(draftText, lang);
  const b = tokenizeForLocale(editedText, lang);
  const m = a.length;
  const n = b.length;

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i] === b[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const raw: DiffSegment[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      raw.push({ type: "unchanged", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      raw.push({ type: "removed", text: a[i] });
      i++;
    } else {
      raw.push({ type: "added", text: b[j] });
      j++;
    }
  }
  while (i < m) {
    raw.push({ type: "removed", text: a[i++] });
  }
  while (j < n) {
    raw.push({ type: "added", text: b[j++] });
  }

  // Merge adjacent segments of the same type
  const merged: DiffSegment[] = [];
  for (const seg of raw) {
    const prev = merged[merged.length - 1];
    if (prev && prev.type === seg.type) {
      prev.text += seg.text;
    } else {
      merged.push({ ...seg });
    }
  }
  return merged;
}
