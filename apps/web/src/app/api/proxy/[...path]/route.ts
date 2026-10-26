/**
 * Next.js Route-Handler Proxy (`apps/web/src/app/api/proxy/[...path]/route.ts`)
 *
 * Per Phase 8 User Answer 3:
 * - Forwards the `httpOnly, Secure, SameSite=Lax` session cookie (`alba_session`)
 *   to FastAPI as an `Authorization: Bearer ...` header so tokens are never readable
 *   by browser JavaScript and never placed in `NEXT_PUBLIC_*` variables or query strings.
 * - Preserves streaming `ReadableStream` bodies for SSE (`text/event-stream`).
 */

import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const FASTAPI_INTERNAL_URL = process.env.FASTAPI_INTERNAL_URL ?? "http://127.0.0.1:8000";

async function proxyToFastAPI(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  const { path } = await context.params;
  const targetPath = path.map((seg) => encodeURIComponent(seg)).join("/");
  const search = req.nextUrl.search || "";
  const upstreamUrl = `${FASTAPI_INTERNAL_URL}/api/${targetPath}${search}`;

  const cookieStore = await cookies();
  const sessionToken = cookieStore.get("alba_session")?.value;

  const headers = new Headers();
  for (const key of ["content-type", "accept", "idempotency-key", "last-event-id", "x-tenant-id", "x-trace-id"]) {
    const val = req.headers.get(key);
    if (val) {
      headers.set(key, val);
    }
  }
  if (sessionToken) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    body: req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined,
    cache: "no-store",
  };

  const upstreamRes = await fetch(upstreamUrl, init);
  const contentType = upstreamRes.headers.get("content-type") ?? "application/json";

  if (contentType.includes("text/event-stream") && upstreamRes.body) {
    return new Response(upstreamRes.body, {
      status: upstreamRes.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const payload = await upstreamRes.text();
  return new NextResponse(payload, {
    status: upstreamRes.status,
    headers: { "Content-Type": contentType },
  });
}

export const GET = proxyToFastAPI;
export const POST = proxyToFastAPI;
export const PUT = proxyToFastAPI;
export const DELETE = proxyToFastAPI;
