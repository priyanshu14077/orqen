import { describe, expect, it } from "vitest";

import { safeNext } from "../safe-next";
import { forwardQuery, match, sameOrigin } from "./bff";

const ID = "89800682-c7a3-5229-a535-25d4eb0cdeab";

describe("the /api/gw allow-list", () => {
  it("passes only listed method and path pairs", () => {
    expect(match("GET", `v1/submissions/${ID}/events`)?.stream).toBe(true);
    expect(match("POST", "v1/submissions")).toBeDefined();
    expect(match("DELETE", "v1/submissions")).toBeUndefined();
    expect(match("GET", "v1/admin")).toBeUndefined();
    expect(match("GET", `v1/submissions/${ID}/../../admin`)).toBeUndefined();
    expect(match("GET", "v1/problems/not-a-uuid")).toBeUndefined();
  });

  it("forwards only the query keys a route names", () => {
    const rule = match("GET", "v1/submissions")!;
    expect(forwardQuery(rule, new URLSearchParams("limit=5&debug=1"))).toBe("?limit=5");
  });

  it("checks Origin exactly", () => {
    expect(sameOrigin("http://localhost:3000", "http://localhost:3000")).toBe(true);
    expect(sameOrigin("http://localhost:3000.evil.example", "http://localhost:3000")).toBe(false);
    expect(sameOrigin(null, "http://localhost:3000")).toBe(false);
  });
});

describe("safeNext", () => {
  it.each([
    ["/s/abc", "/s/abc"],
    ["//evil.example", "/"],
    ["https://evil.example", "/"],
    ["/\\evil.example", "/"],
    [null, "/"],
  ])("%s → %s", (input, out) => expect(safeNext(input)).toBe(out));
});
