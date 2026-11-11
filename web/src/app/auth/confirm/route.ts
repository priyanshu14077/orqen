import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/safe-next";
import { env } from "@/lib/server/env";
import { provision } from "@/lib/server/provision";
import { supabaseServer } from "@/lib/server/supabase";

export const dynamic = "force-dynamic";

const TYPES = new Set<EmailOtpType>(["signup", "email", "recovery", "email_change"]);

/**
 * Links in Supabase emails land here: sign-up confirmation and password reset.
 *
 * With the email templates pointed at `/auth/confirm?token_hash=…&type=…`, the link
 * works in any browser. The default `{{ .ConfirmationURL }}` template returns a PKCE
 * `code` instead, which only works in the browser that asked for the email.
 */
export async function GET(request: NextRequest) {
  const site = env.siteUrl();
  const q = request.nextUrl.searchParams;
  const next = safeNext(q.get("next"));
  const tokenHash = q.get("token_hash");
  const type = q.get("type") as EmailOtpType | null;
  const code = q.get("code");

  const supabase = await supabaseServer();
  let accessToken: string | undefined;
  if (tokenHash && type && TYPES.has(type)) {
    const { data, error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (!error) accessToken = data.session?.access_token;
  } else if (code) {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) accessToken = data.session?.access_token;
  }
  if (!accessToken) return NextResponse.redirect(new URL("/login?error=link", site));
  if (!(await provision(supabase, accessToken))) {
    return NextResponse.redirect(new URL("/login?error=account", site));
  }
  const dest = type === "recovery" ? "/reset-password" : next;
  return NextResponse.redirect(new URL(dest, site));
}
