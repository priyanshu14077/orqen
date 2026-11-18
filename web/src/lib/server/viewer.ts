import "server-only";

import { cache } from "react";

import type { Me } from "@/lib/api/types";

import { gateway } from "./gateway";

/** The signed-in user's Orqen account; `gateway` creates it if the callback missed it. */
export const getMe = cache((): Promise<Me> => gateway<Me>("/v1/me"));
