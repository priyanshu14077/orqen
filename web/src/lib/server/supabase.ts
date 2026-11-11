import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { SESSION_COOKIE } from "./cookies";
import { env } from "./env";

/** A Supabase client for one request in a server component, route or action. */
export async function supabaseServer() {
  const store = await cookies();
  return createServerClient(env.supabaseUrl(), env.supabaseKey(), {
    cookieOptions: SESSION_COOKIE,
    auth: { flowType: "pkce" },
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list) => {
        try {
          for (const { name, value, options } of list) {
            store.set(name, value, { ...options, ...SESSION_COOKIE });
          }
        } catch {
          // Server components can't set cookies; src/proxy.ts refreshes the session.
        }
      },
    },
  });
}
