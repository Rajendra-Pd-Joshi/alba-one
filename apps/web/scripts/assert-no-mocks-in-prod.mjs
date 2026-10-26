#!/usr/bin/env node
/**
 * CI & Build Guard (`apps/web/scripts/assert-no-mocks-in-prod.mjs`)
 * Fails the build immediately if `NODE_ENV === "production"` and `NEXT_PUBLIC_USE_MOCKS === "true"`.
 */
if (
  process.env.NODE_ENV === "production" &&
  process.env.NEXT_PUBLIC_USE_MOCKS === "true" &&
  process.env.ALLOW_E2E_MOCK_BUILD !== "1"
) {
  console.error(
    "ERROR: Production build rejected because NEXT_PUBLIC_USE_MOCKS=true is set."
  );
  process.exit(1);
}
