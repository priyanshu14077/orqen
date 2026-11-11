import type { Verdict } from "@/lib/api/types";

/**
 * A scripted judge log for the landing hero: submissions of 20 tests each, one line
 * per test, then a summary line. Seeded, so the server and the browser render the
 * same first lines and hydration matches.
 */

export type TestLine = {
  kind: "test";
  key: number;
  ts: string;
  test: number;
  scope: "sample" | "hidden";
  verdict: Verdict;
  tokens: number;
  steps: number;
  latency: string;
  retry?: string;
};
export type SummaryLine = {
  kind: "summary";
  key: number;
  submission: number;
  score: number;
  passed: number;
  tokens: number;
};
export type Line = TestLine | SummaryLine;

export type Progress = { submission: number; test: number; score: number; tokens: number };

export const TESTS = 20;
const SAMPLES = 3;
const POINTS = 50;
const WEIGHTS: [Verdict, number][] = [
  ["PASS", 14],
  ["FAIL", 3],
  ["TLE", 1],
  ["MLE", 1],
  ["ERROR", 1],
  ["BUDGET", 1],
];
const TOTAL_WEIGHT = WEIGHTS.reduce((a, [, w]) => a + w, 0);

/** mulberry32: a small, fast, seedable PRNG. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clock(seconds: number): string {
  const h = Math.floor(seconds / 3600) % 24;
  const m = Math.floor((seconds % 3600) / 60);
  const s = (seconds % 60).toFixed(3).padStart(6, "0");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s}`;
}

export function createReplay(seed = 48213) {
  const rand = rng(seed);
  let key = 0;
  let submission = seed;
  let test = 0;
  let score = 0;
  let passed = 0;
  let tokens = 0;
  let seconds = 14 * 3600 + 3 * 60;
  let retrying = 0; // 0 none, 1–2 the attempt being retried, -1 just retried

  const pick = (): Verdict => {
    let r = rand() * TOTAL_WEIGHT;
    for (const [v, w] of WEIGHTS) if ((r -= w) < 0) return v;
    return "PASS";
  };

  function next(): Line {
    key += 1;
    if (test === TESTS) {
      const line: SummaryLine = { kind: "summary", key, submission, score, passed, tokens };
      submission += 1;
      test = score = passed = tokens = 0;
      return line;
    }
    seconds += 1.2 + rand() * 2.4;
    // Now and then an infrastructure fault: retried, then the real verdict.
    if (retrying === 0 && test > SAMPLES && rand() < 0.06) {
      retrying = 1;
    }
    if (retrying > 0) {
      const attempt = retrying;
      retrying = attempt < 2 ? attempt + 1 : -1; // -1: the next line is the real verdict
      return {
        kind: "test",
        key,
        ts: clock(seconds),
        test: test + 1,
        scope: "hidden",
        verdict: "SYSTEM_ERROR",
        tokens: 0,
        steps: 0,
        latency: "—",
        retry: `retry ${attempt}/3`,
      };
    }
    retrying = 0;
    test += 1;
    const verdict = pick();
    const spent = verdict === "BUDGET" ? 60_000 : 2_000 + Math.floor(rand() * 18_000);
    tokens += spent;
    if (verdict === "PASS") {
      score += POINTS;
      passed += 1;
    }
    return {
      kind: "test",
      key,
      ts: clock(seconds),
      test,
      scope: test <= SAMPLES ? "sample" : "hidden",
      verdict,
      tokens: spent,
      steps: 3 + Math.floor(rand() * 30),
      latency: verdict === "TLE" ? "120.0s" : `${(4 + rand() * 70).toFixed(1)}s`,
    };
  }

  const progress = (): Progress => ({ submission, test, score, tokens });
  return { next, progress };
}
