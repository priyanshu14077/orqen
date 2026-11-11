import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/server/cookies";
import { contentSecurityPolicy } from "@/lib/server/csp";

// The landing page, sign-in and the auth routes. Everything else needs a session.
const PUBLIC = [/^\/$/, /^\/login$/, /^\/auth\//];

/**
 * Runs before every page and API request:
 * 0. Redirects other host names to SITE_URL's host.
 * 1. Refreshes the Supabase session when the access token is close to expiry, and
 *    writes the new httpOnly cookies to both the request and the response.
 * 2. Sends signed-out visitors to /login (API calls get a 401 instead).
 * 3. Sets a per-request nonce Content-Security-Policy.
 *
 * This is a convenience gate, not the security boundary: every server route checks the
 * session itself, and the gateway verifies the token again.
 */
export async function proxy(request: NextRequest) {
  // One canonical host. Sign-in sets its PKCE cookie on this host, so a sign-in started
  // on another name (localhost vs orqen.localhost) could never complete.
  const site = process.env.SITE_URL ? new URL(process.env.SITE_URL) : null;
  // nextUrl.host is the server's bind address in dev, not what the browser asked for.
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (site && host && host !== site.host) {
    return NextResponse.redirect(new URL(request.nextUrl.pathname + request.nextUrl.search, site), 308);
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const pending: { name: string; value: string; options: object }[] = [];
  const cacheHeaders: Record<string, string> = {};
  const supabase = createServerClient(
    process.env.SUPABASE_URL ?? "",
    process.env.SUPABASE_PUBLISHABLE_KEY ?? "",
    {
      cookieOptions: SESSION_COOKIE,
      auth: { flowType: "pkce" },
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (list, headers) => {
          for (const { name, value, options } of list) {
            request.cookies.set(name, value);
            pending.push({ name, value, options: { ...options, ...SESSION_COOKIE } });
          }
          Object.assign(cacheHeaders, headers);
        },
      },
    },
  );
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims?.sub);
  const path = request.nextUrl.pathname;

  // Rebuild the forwarded headers after any cookie refresh, so pages see new tokens.
  requestHeaders.set("cookie", request.cookies.toString());
  let response: NextResponse;
  if (!signedIn && !PUBLIC.some((re) => re.test(path))) {
    if (path.startsWith("/api/")) {
      response = NextResponse.json({ detail: "not signed in" }, { status: 401 });
    } else {
      const login = new URL("/login", request.url);
      login.searchParams.set("next", path + request.nextUrl.search);
      response = NextResponse.redirect(login);
    }
  } else if (signedIn && path === "/login") {
    response = NextResponse.redirect(new URL("/problems", request.url));
  } else {
    response = NextResponse.next({ request: { headers: requestHeaders } });
  }

  for (const c of pending) response.cookies.set(c.name, c.value, c.options);
  for (const [k, v] of Object.entries(cacheHeaders)) response.headers.set(k, v);
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|bg/|favicon.ico|robots.txt).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
