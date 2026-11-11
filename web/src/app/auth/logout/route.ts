import { type NextRequest, NextResponse } from "next/server";

import { sameOrigin } from "@/lib/server/bff";
import { env } from "@/lib/server/env";
import { supabaseServer } from "@/lib/server/supabase";

export const dynamic = "force-dynamic";

/** Sign out: a POST from this site only, so another site can't log a user out. */
export async function POST(request: NextRequest) {
  if (!sameOrigin(request.headers.get("origin"), env.siteUrl())) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }
  const supabase = await supabaseServer();
  await supabase.auth.signOut({ scope: "local" });
  return NextResponse.redirect(new URL("/login", env.siteUrl()), { status: 303 });
}
