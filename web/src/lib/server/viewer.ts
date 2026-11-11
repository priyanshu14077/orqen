import "server-only";

import { cache } from "react";

import type { Me } from "@/lib/api/types";

import { gateway, GatewayError } from "./gateway";

/** The signed-in user's Orqen account, created on first use if the callback missed it. */
export const getMe = cache(async (): Promise<Me> => {
  try {
    return await gateway<Me>("/v1/me");
  } catch (err) {
    if (err instanceof GatewayError && err.status === 403) {
      return gateway<Me>("/v1/me", { method: "POST" });
    }
    throw err;
  }
});
