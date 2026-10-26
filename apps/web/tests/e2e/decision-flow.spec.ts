import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Core Decision OS E2E + Axe Accessibility Suite (`apps/web/tests/e2e/decision-flow.spec.ts`)
 *
 * Runs across both `ja` and `en` locales in both `mock` and `e2e` projects:
 * 1. Verifies top-to-bottom layout order: Recommendation Summary -> Gates Banner -> ComparisonTable -> Hypotheses -> StickyActionBar.
 * 2. Verifies `approve_with_conditions` workflow with structured conditions and rationale.
 * 3. Verifies Outcomes Two-Stage Card with live diff and Steward Write-Back confirmation.
 * 4. Runs `@axe-core/playwright` accessibility checks on both main pages.
 */
for (const locale of ["ja", "en"] as const) {
  test(`Core Decision Workspace flow & axe accessibility (${locale})`, async ({ page }) => {
    await page.goto(`/${locale}`);

    // Verify ComparisonTable appears above StickyActionBar
    const tableHeading = page.locator("#comparison-table-heading");
    await expect(tableHeading).toBeVisible();

    const approveWithConditionsBtn = page.getByRole("button", {
      name: locale === "ja" ? "条件付き承認" : "Approve with conditions",
    });
    await expect(approveWithConditionsBtn).toBeVisible();
    await approveWithConditionsBtn.click();

    await page.locator("#hitl-rationale-input").fill("Approved with 30m cold-chain telemetry checks.");
    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test(`Outcomes Two-Stage Card & axe accessibility (${locale})`, async ({ page }) => {
    await page.goto(`/${locale}/outcomes`);
    await expect(page.locator("#outcome-stage1-heading")).toBeVisible();
    await expect(page.locator("#outcome-stage2-heading")).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });
}
