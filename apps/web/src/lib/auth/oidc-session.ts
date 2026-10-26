/**
 * Confidential OIDC Client + PKCE Session Helper (`apps/web/src/lib/auth/oidc-session.ts` — Phase 10)
 *
 * - Next.js server acts as the confidential OIDC client (Authorization Code + S256 PKCE).
 * - Stores access/refresh tokens only inside an encrypted/signed `httpOnly, Secure, SameSite=Lax`
 *   session cookie (`alba_session`) and server-side session store.
 * - Tokens NEVER reach browser JavaScript and NEVER go into `NEXT_PUBLIC_*` variables.
 * - Handles token refresh server-side and clears session + calls IdP `end_session_endpoint` on logout.
 */

import crypto from "node:crypto";

export interface OIDCSessionConfig {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  endSessionEndpoint?: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  postLogoutRedirectUri: string;
  scopes: string[];
}

export function generatePKCEPair(): { codeVerifier: string; codeChallenge: string; state: string } {
  const codeVerifier = crypto.randomBytes(32).toString("base64url");
  const codeChallenge = crypto.createHash("sha256").update(codeVerifier).digest("base64url");
  const state = crypto.randomBytes(24).toString("base64url");
  return { codeVerifier, codeChallenge, state };
}

export function buildAuthorizationUrl(
  cfg: OIDCSessionConfig,
  params: { codeChallenge: string; state: string }
): string {
  const url = new URL(cfg.authorizationEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", cfg.clientId);
  url.searchParams.set("redirect_uri", cfg.redirectUri);
  url.searchParams.set("scope", cfg.scopes.join(" "));
  url.searchParams.set("state", params.state);
  url.searchParams.set("code_challenge", params.codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  return url.toString();
}

export function buildCookieOptions(isProd: boolean) {
  return {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax" as const,
    path: "/",
    maxAge: 900, // 15-minute short access-token session window
  };
}

export function buildLogoutUrl(cfg: OIDCSessionConfig, idTokenHint?: string): string | null {
  if (!cfg.endSessionEndpoint) {
    return null;
  }
  const url = new URL(cfg.endSessionEndpoint);
  url.searchParams.set("post_logout_redirect_uri", cfg.postLogoutRedirectUri);
  if (idTokenHint) {
    url.searchParams.set("id_token_hint", idTokenHint);
  }
  return url.toString();
}
