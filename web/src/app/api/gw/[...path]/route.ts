import { type NextRequest, NextResponse } from "next/server";

import { forwardQuery, match, sameOrigin } from "@/lib/server/bff";
import { env } from "@/lib/server/env";
import { getSession } from "@/lib/server/session";

export const dynamic = "force-dynamic";

const MAX_BODY = 64 * 1024;
const FORWARD_REQUEST = ["content-type", "idempotency-key", "last-event-id"];
const FORWARD_RESPONSE = ["content-type", "cache-control", "location", "x-trace-id"];

/**
 * The browser's only route to the gateway. It checks the path against an allow-list,
 * checks Origin on mutations, attaches the user's access token from the httpOnly
 * session cookie, and streams the response back (including Server-Sent Events).
 */
async function forward(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  const rule = match(request.method, path);
  if (!rule) return NextResponse.json({ detail: "not found" }, { status: 404 });

  if (request.method !== "GET") {
    if (!sameOrigin(request.headers.get("origin"), env.siteUrl())) {
      return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ detail: "expected application/json" }, { status: 415 });
    }
  }

  const session = await getSession();
  if (!session) return NextResponse.json({ detail: "not signed in" }, { status: 401 });

  const headers = new Headers({ Authorization: `Bearer ${session.accessToken}` });
  for (const name of FORWARD_REQUEST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value.slice(0, 256));
  }
  let body: string | undefined;
  if (request.method !== "GET") {
    body = await request.text();
    if (body.length > MAX_BODY) {
      return NextResponse.json({ detail: "request too large" }, { status: 413 });
    }
  }

  const upstream = await fetch(
    `${env.gatewayUrl()}/${path}${forwardQuery(rule, request.nextUrl.searchParams)}`,
    { method: request.method, headers, body, cache: "no-store", signal: request.signal },
  ).catch(() => null);
  if (!upstream) return NextResponse.json({ detail: "gateway unreachable" }, { status: 502 });

  const out = new Headers();
  for (const name of FORWARD_RESPONSE) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  if (rule.stream) {
    out.set("Cache-Control", "no-cache, no-transform");
    out.set("X-Accel-Buffering", "no");
  } else {
    out.set("Cache-Control", "private, no-store");
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST };
