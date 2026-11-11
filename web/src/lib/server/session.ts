import "server-only";

import { cache } from "react";

import { supabaseServer } from "./supabase";

export type Session = { userId: string; email: string | null; accessToken: string };

/**
 * The signed-in user for this request, or null.
 *
 * `getClaims()` verifies the access token's signature against the project's public
 * keys before anything is trusted; the token itself is then forwarded to the gateway,
 * which verifies it again. `cache` makes this one lookup per request.
 */
export const getSession = cache(async (): Promise<Session | null> => {
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims?.sub) return null;
  const { data: current } = await supabase.auth.getSession();
  const accessToken = current.session?.access_token;
  if (!accessToken) return null;
  return {
    userId: data.claims.sub,
    email: typeof data.claims.email === "string" ? data.claims.email : null,
    accessToken,
  };
});
