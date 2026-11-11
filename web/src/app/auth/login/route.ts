import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/safe-next";
import { env } from "@/lib/server/env";
import { supabaseServer } from "@/lib/server/supabase";

export const dynamic = "force-dynamic";

const PROVIDERS = new Set(["github"] as const);
type Provider = typeof PROVIDERS extends Set<infer P> ? P : never;

/**
 * Starts OAuth on the server. Supabase stores the PKCE code verifier in an httpOnly
 * cookie here, and the callback exchanges the code with it, so a code stolen from the
 * redirect URL is useless without this browser's cookie.
 */
export async function GET(request: NextRequest) {
  const provider = request.nextUrl.searchParams.get("provider") ?? "";
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  if (!PROVIDERS.has(provider as Provider)) {
    return NextResponse.redirect(new URL("/login?error=provider", env.siteUrl()));
  }
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: provider as Provider,
    options: {
      redirectTo: `${env.siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
      skipBrowserRedirect: true,
      scopes: "read:user user:email",
    },
  });
  if (error || !data.url) {
    return NextResponse.redirect(new URL("/login?error=start", env.siteUrl()));
  }
  return NextResponse.redirect(data.url, { status: 303 });
}
