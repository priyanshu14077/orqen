import { describe, expect, it } from "vitest";

import { createReplay, type Line, TESTS } from "./replay";

const take = (n: number, seed?: number): Line[] => {
  const r = createReplay(seed);
  return Array.from({ length: n }, () => r.next());
};

describe("createReplay", () => {
  it("is deterministic for a seed, so server and client render the same lines", () => {
    expect(take(60)).toEqual(take(60));
    expect(take(60, 1)).not.toEqual(take(60, 2));
  });

  it("runs every test of a submission once, then summarises it", () => {
    const lines = take(80);
    const end = lines.findIndex((l) => l.kind === "summary");
    const tests = lines.slice(0, end).filter((l) => l.kind === "test" && !l.retry);
    expect(tests.map((l) => (l.kind === "test" ? l.test : 0))).toEqual(
      Array.from({ length: TESTS }, (_, i) => i + 1),
    );
    const summary = lines[end];
    if (summary.kind !== "summary") throw new Error("expected a summary");
    const passes = tests.filter((l) => l.kind === "test" && l.verdict === "PASS").length;
    expect(summary.passed).toBe(passes);
    expect(summary.score).toBe(passes * 50);
  });

  it("follows a retried system error with a real verdict for the same test", () => {
    const lines = take(2000);
    const retries = lines.filter((l) => l.kind === "test" && l.retry);
    expect(retries.length).toBeGreaterThan(0);
    for (let i = 0; i < lines.length - 1; i++) {
      const l = lines[i];
      if (l.kind === "test" && l.retry === "retry 2/3") {
        const after = lines[i + 1];
        expect(after.kind === "test" && !after.retry && after.test === l.test).toBe(true);
      }
    }
  });
});
