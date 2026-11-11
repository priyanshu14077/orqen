/**
 * The Content-Security-Policy for one response. Scripts run only with this request's
 * nonce ('strict-dynamic' lets them load their own chunks). The browser may connect
 * only to this origin: Supabase and the gateway are reached through the server.
 * `style-src-attr 'unsafe-inline'` allows React `style` props (meter widths, bar
 * lengths) but not <style> blocks or stylesheets from elsewhere.
 */
export function contentSecurityPolicy(nonce: string, dev: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Dev tooling injects <style> tags without a nonce; production styles are files.
    dev ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}
