"use client";

export type ApiResult<T> = { ok: true; status: number; data: T } | { ok: false; status: number; detail: string };

/**
 * Browser calls go to /api/gw, never to the gateway: the Next.js server attaches the
 * session token from the httpOnly cookie. Same-origin fetches carry the cookie and an
 * Origin header, which the route checks on mutations.
 */
export async function api<T>(
  path: string,
  init: { method?: "GET" | "POST"; body?: unknown; idempotencyKey?: string } = {},
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.idempotencyKey) headers["Idempotency-Key"] = init.idempotencyKey;
  try {
    const resp = await fetch(`/api/gw/${path.replace(/^\//, "")}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
      credentials: "same-origin",
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) return { ok: false, status: resp.status, detail: String(data.detail ?? resp.statusText) };
    return { ok: true, status: resp.status, data: data as T };
  } catch {
    return { ok: false, status: 0, detail: "network error" };
  }
}
