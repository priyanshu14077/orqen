import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/safe-next";
import { env } from "@/lib/server/env";
import { provision } from "@/lib/server/provision";
import { supabaseServer } from "@/lib/server/supabase";

export const dynamic = "force-dynamic";

/**
 * OAuth comes back here. Exchange the code for a session (PKCE, verifier from the
 * httpOnly cookie), then create the Orqen account if this is the first sign-in.
 */
export async function GET(request: NextRequest) {
  const site = env.siteUrl();
  const code = request.nextUrl.searchParams.get("code");
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  if (!code) return NextResponse.redirect(new URL("/login?error=callback", site));

  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);
  if (error || !data.session) return NextResponse.redirect(new URL("/login?error=exchange", site));
  if (!(await provision(supabase, data.session.access_token))) {
    return NextResponse.redirect(new URL("/login?error=account", site));
  }
  return NextResponse.redirect(new URL(next, site));
}
