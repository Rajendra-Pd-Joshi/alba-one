#!/usr/bin/env node
/**
 * Web Server Startup Fail-Closed Check (`apps/web/scripts/check-startup.mjs` — Phase 10)
 *
 * Executed before `node server.js` starts in the Next.js container.
 * 1. Treats an unset or unknown `APP_ENV` as `"production"`.
 * 2. Refuses to start when `APP_ENV` is `staging` or `production` and `NEXT_PUBLIC_USE_MOCKS=true`
 *    is set in the environment OR inlined in the Next.js standalone build output (`.next`).
 * 3. Ensures no OIDC client secret or token was placed into any `NEXT_PUBLIC_*` variable.
 */
import fs from "node:fs";
import path from "node:path";

const VALID_ENVS = new Set(["development", "test", "staging", "production"]);
const rawEnv = (process.env.APP_ENV || "").trim().toLowerCase();
const violations = [];

let effectiveEnv = rawEnv;
if (!rawEnv || !VALID_ENVS.has(rawEnv)) {
  effectiveEnv = "production";
  violations.push(
    `APP_ENV='${rawEnv}' is unset or invalid; treating as production-strict.`
  );
}

if (effectiveEnv === "staging" || effectiveEnv === "production") {
  if (
    String(process.env.NEXT_PUBLIC_USE_MOCKS || "").toLowerCase() === "true"
  ) {
    violations.push(
      "NEXT_PUBLIC_USE_MOCKS=true is forbidden in staging/production."
    );
  }

  for (const key of Object.keys(process.env)) {
    if (
      key.startsWith("NEXT_PUBLIC_") &&
      /(SECRET|TOKEN|PRIVATE_KEY|API_KEY)/i.test(key)
    ) {
      violations.push(
        `Sensitive variable ${key} must never use the NEXT_PUBLIC_ prefix.`
      );
    }
  }

  const buildMetaPath = path.join(process.cwd(), ".next", "required-server-files.json");
  if (fs.existsSync(buildMetaPath)) {
    const rawMeta = fs.readFileSync(buildMetaPath, "utf-8");
    if (rawMeta.includes('"NEXT_PUBLIC_USE_MOCKS":"true"')) {
      violations.push(
        "Build metadata (.next/required-server-files.json) contains inlined NEXT_PUBLIC_USE_MOCKS=true."
      );
    }
  }
}

if (violations.length > 0) {
  console.error(
    `ALBA ONE Web Startup Check Failed (${violations.length} violation(s)):\n` +
      violations.map((v, i) => `  - [${i + 1}] ${v}`).join("\n")
  );
  process.exit(1);
}
