/**
 * Production Build Guard & Standalone Output Config (`apps/web/next.config.mjs`)
 *
 * - Enforces `output: "standalone"` for minimal read-only container runtime.
 * - Fails the build step if `NODE_ENV === "production"` and `NEXT_PUBLIC_USE_MOCKS === "true"`.
 * - Does NOT set conflicting security/CSP headers here; security headers are set in ONE place
 *   at the edge reverse proxy (`deploy/docker/Caddyfile` and Kubernetes Ingress).
 */
export function assertProductionBuildRejectsMocks(env = process.env) {
  if (env.NODE_ENV === "production" && env.NEXT_PUBLIC_USE_MOCKS === "true" && env.ALLOW_E2E_MOCK_BUILD !== "1") {
    throw new Error(
      "FATAL: NEXT_PUBLIC_USE_MOCKS=true is forbidden when NODE_ENV=production. " +
        "Unset NEXT_PUBLIC_USE_MOCKS before building for production."
    );
  }
}

assertProductionBuildRejectsMocks(process.env);

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
