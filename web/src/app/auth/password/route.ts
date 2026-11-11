import { type NextRequest, NextResponse } from "next/server";

import { PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";
import { safeNext } from "@/lib/safe-next";
import { sameOrigin } from "@/lib/server/bff";
import { env } from "@/lib/server/env";
import { provision } from "@/lib/server/provision";
import { supabaseServer } from "@/lib/server/supabase";

export const dynamic = "force-dynamic";

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$/;

type Intent = "signin" | "signup" | "forgot" | "update";

/**
 * Email and password, as plain form posts: no client JavaScript holds a token.
 *
 *   signin   email + password → session → Orqen account → `next`
 *   signup   sends a confirmation email (or signs in, if confirmation is off)
 *   forgot   sends a reset link that lands on /reset-password
 *   update   sets a new password for the signed-in user
 *
 * Messages never say whether an email is registered.
 */
export async function POST(request: NextRequest) {
  const site = env.siteUrl();
  const to = (path: string) => NextResponse.redirect(new URL(path, site), { status: 303 });

  if (!sameOrigin(request.headers.get("origin"), site)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }
  if (Number(request.headers.get("content-length") ?? 0) > 4096) {
    return NextResponse.json({ detail: "request too large" }, { status: 413 });
  }
  const form = await request.formData().catch(() => null);
  const field = (k: string) => {
    const v = form?.get(k);
    return typeof v === "string" ? v : "";
  };
  const intent = field("intent") as Intent;
  const email = field("email").trim().toLowerCase();
  const password = field("password");
  const next = safeNext(field("next"));
  const back = (mode: string, key: string, kind: "error" | "notice" = "error") =>
    to(`/login?mode=${mode}&${kind}=${key}&next=${encodeURIComponent(next)}`);

  const supabase = await supabaseServer();
  const badPassword = password.length < PASSWORD_MIN || password.length > PASSWORD_MAX;

  switch (intent) {
    case "signin": {
      if (!EMAIL.test(email) || !password) return back("signin", "credentials");
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error?.code === "email_not_confirmed") return back("signin", "unconfirmed");
      if (error?.status === 429) return back("signin", "rate");
      if (error || !data.session) return back("signin", "credentials");
      if (!(await provision(supabase, data.session.access_token))) return back("signin", "account");
      return to(next);
    }
    case "signup": {
      if (!EMAIL.test(email)) return back("signup", "email");
      if (badPassword) return back("signup", "weak");
      if (password !== field("confirm")) return back("signup", "mismatch");
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${site}/auth/confirm?next=${encodeURIComponent(next)}` },
      });
      if (error?.code === "weak_password") return back("signup", "weak");
      if (error?.status === 429) return back("signup", "rate");
      if (error) return back("signup", "signup");
      if (data.session) {
        // Email confirmation is off: the user is signed in already.
        if (!(await provision(supabase, data.session.access_token))) return back("signin", "account");
        return to(next);
      }
      return back("signin", "confirm", "notice");
    }
    case "forgot": {
      if (!EMAIL.test(email)) return back("forgot", "email");
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${site}/auth/confirm?next=/reset-password`,
      });
      if (error?.status === 429) return back("forgot", "rate");
      return back("signin", "reset", "notice");
    }
    case "update": {
      if (badPassword) return to("/reset-password?error=weak");
      if (password !== field("confirm")) return to("/reset-password?error=mismatch");
      const { error } = await supabase.auth.updateUser({ password });
      if (error?.code === "same_password") return to("/reset-password?error=same");
      if (error) return to("/reset-password?error=update");
      return to("/?notice=password");
    }
    default:
      return back("signin", "start");
  }
}
