import type { CookieOptions } from "@supabase/ssr";

/**
 * Session cookies are httpOnly: no script in the browser can read the access or
 * refresh token. The browser never talks to Supabase or the gateway directly; the
 * Next.js server does, so nothing client-side needs the tokens. SameSite=Lax keeps
 * them off cross-site POSTs.
 */
export const SESSION_COOKIE: CookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax",
  path: "/",
};
