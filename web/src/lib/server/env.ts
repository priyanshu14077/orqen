import "server-only";

/**
 * Server-only configuration. Read lazily so a build without these variables still
 * succeeds; a request that needs one fails loudly instead.
 */
function need(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set; see web/.env.example`);
  return value;
}

export const env = {
  siteUrl: () => need("SITE_URL").replace(/\/$/, ""),
  supabaseUrl: () => need("SUPABASE_URL").replace(/\/$/, ""),
  supabaseKey: () => {
    const key = need("SUPABASE_PUBLISHABLE_KEY");
    if (key.startsWith("sb_secret_")) {
      throw new Error("SUPABASE_PUBLISHABLE_KEY holds a secret key; use the publishable one");
    }
    return key;
  },
  gatewayUrl: () => need("ORQEN_GATEWAY_URL").replace(/\/$/, ""),
};
