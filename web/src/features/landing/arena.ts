import "server-only";

import { cache } from "react";

import type { components } from "@/lib/api/schema";
import { env } from "@/lib/server/env";

export type Arena = components["schemas"]["Arena"];

/**
 * The public problem set and leaderboard, from the gateway, with no user token.
 * Null when the gateway is unreachable: the page then renders without live numbers.
 * The page streams these sections in, so a slow gateway never holds up first paint.
 * `cache` shares one fetch between the hero's numbers and the sections below.
 */
export const getArena = cache(async (): Promise<Arena | null> => {
  try {
    const res = await fetch(`${env.gatewayUrl()}/v1/public/arena`, {
      next: { revalidate: 30 },
      signal: AbortSignal.timeout(8000),
    });
    return res.ok ? ((await res.json()) as Arena) : null;
  } catch {
    return null;
  }
});
