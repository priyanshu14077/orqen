import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { env } from "./env";
import { getSession } from "./session";

/** The gateway's 403 detail for a signed-in user who has no Orqen account yet. */
export const NO_ACCOUNT = "no Orqen account yet: call POST /v1/me first";

/**
 * Create the Orqen account (idempotent on the gateway). `cache` makes it one call per
 * request, however many gateway calls in the render found the account missing.
 */
const ensureAccount = cache(async (accessToken: string): Promise<boolean> => {
  const resp = await fetch(`${env.gatewayUrl()}/v1/me`, {
    method: "POST",
    cache: "no-store",
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
  }).catch(() => null);
  return Boolean(resp?.ok);
});

export class GatewayError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`gateway ${status}: ${detail}`);
  }
}

/**
 * Call the gateway as the signed-in user, from the server. Redirects to /login when
 * there is no session or the gateway rejects the token.
 *
 * A valid Supabase session can outlive its Orqen account (a new database, or a sign-in
 * whose callback failed to create it). The first call that finds the account missing
 * creates it and retries once, so every page works without depending on which of its
 * parallel calls happens to create the account first.
 */
export async function gateway<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = await getSession();
  if (!session) redirect("/login");
  const call = () =>
    fetch(`${env.gatewayUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...init.headers,
        Authorization: `Bearer ${session.accessToken}`,
        Accept: "application/json",
      },
    });

  let resp = await call();
  let body = resp.ok ? null : await resp.json().catch(() => ({}));
  if (resp.status === 403 && body?.detail === NO_ACCOUNT && (await ensureAccount(session.accessToken))) {
    resp = await call();
    body = resp.ok ? null : await resp.json().catch(() => ({}));
  }
  if (resp.status === 401) redirect("/login?error=session");
  if (!resp.ok) throw new GatewayError(resp.status, String(body?.detail ?? resp.statusText));
  return (await resp.json()) as T;
}
