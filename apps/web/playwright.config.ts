import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright Configuration (`apps/web/playwright.config.ts`)
 *
 * Per Phase 8 User Answer 3:
 * Two distinct projects:
 * 1. `mock`: runs in CI without a backend (`NEXT_PUBLIC_USE_MOCKS=true`).
 * 2. `e2e`: runs against `docker compose` with the real FastAPI backend (`NEXT_PUBLIC_USE_MOCKS=false`).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "mock",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
    {
      name: "e2e",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
