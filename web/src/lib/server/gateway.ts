import "server-only";

import { redirect } from "next/navigation";

import { env } from "./env";
import { getSession } from "./session";

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
 */
export async function gateway<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = await getSession();
  if (!session) redirect("/login");
  const resp = await fetch(`${env.gatewayUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...init.headers,
      Authorization: `Bearer ${session.accessToken}`,
      Accept: "application/json",
    },
  });
  if (resp.status === 401) redirect("/login?error=session");
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new GatewayError(resp.status, String(body.detail ?? resp.statusText));
  }
  return (await resp.json()) as T;
}
