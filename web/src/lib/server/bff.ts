/**
 * The allow-list for /api/gw, the browser's only route to the gateway. Anything not
 * listed is refused before a token is attached, so a bug or XSS in the client can't
 * reach other gateway routes with the user's credentials.
 */
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

type Rule = { method: "GET" | "POST"; path: RegExp; query: string[]; stream?: boolean };

export const RULES: Rule[] = [
  { method: "GET", path: /^v1\/me$/, query: [] },
  { method: "POST", path: /^v1\/me$/, query: [] },
  { method: "GET", path: /^v1\/problems$/, query: [] },
  { method: "GET", path: new RegExp(`^v1/problems/${UUID}$`), query: [] },
  { method: "GET", path: new RegExp(`^v1/problems/${UUID}/leaderboard$`), query: ["limit"] },
  { method: "GET", path: /^v1\/submissions$/, query: ["problem_id", "limit"] },
  { method: "POST", path: /^v1\/submissions$/, query: [] },
  { method: "GET", path: new RegExp(`^v1/submissions/${UUID}$`), query: [] },
  {
    method: "GET",
    path: new RegExp(`^v1/submissions/${UUID}/events$`),
    query: ["after"],
    stream: true,
  },
];

export function match(method: string, path: string): Rule | undefined {
  return RULES.find((r) => r.method === method && r.path.test(path));
}

/** Only the query keys the rule names, each value capped. */
export function forwardQuery(rule: Rule, params: URLSearchParams): string {
  const kept = new URLSearchParams();
  for (const key of rule.query) {
    const value = params.get(key);
    if (value !== null && value.length <= 64) kept.set(key, value);
  }
  const q = kept.toString();
  return q ? `?${q}` : "";
}

/**
 * Mutations must come from this site. SameSite=Lax cookies already keep cross-site
 * POSTs unauthenticated; checking Origin as well covers same-site subdomains.
 */
export function sameOrigin(origin: string | null, expected: string): boolean {
  return origin !== null && origin === expected;
}
