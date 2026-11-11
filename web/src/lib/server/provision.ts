import "server-only";

import { env } from "./env";
import type { supabaseServer } from "./supabase";

type Supabase = Awaited<ReturnType<typeof supabaseServer>>;

/**
 * Creates the Orqen account for a fresh Supabase session (idempotent on the gateway).
 * If that fails, the session is dropped, so nobody is left signed in without an account.
 */
export async function provision(supabase: Supabase, accessToken: string): Promise<boolean> {
  const res = await fetch(`${env.gatewayUrl()}/v1/me`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  }).catch(() => null);
  if (res?.ok) return true;
  await supabase.auth.signOut({ scope: "local" });
  return false;
}
