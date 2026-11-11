import { describe, expect, it } from "vitest";

import type { JudgeEvent, Snapshot } from "@/lib/api/types";

import { fromSnapshot, judgeReducer, summarize } from "./reducer";

const base = { ts: "2026-11-11T00:00:00Z", submission_id: "s" };
const status = (seq: number, s: string, total?: number): JudgeEvent => ({ ...base, seq, type: "status", status: s, total });
const test = (seq: number, n: number, verdict: string, attempt = 1): JudgeEvent => ({
  ...base,
  seq,
  type: "test",
  test: n,
  test_case_id: `t${n}`,
  kind: "hidden",
  attempt,
  max_attempts: 3,
  verdict: verdict as never,
  score: verdict === "PASS" ? 1 : 0,
  tokens: 10,
  steps: 1,
  latency_ms: 100,
});

const snapshot = (events: JudgeEvent[], s = "QUEUED"): Snapshot =>
  ({ submission_id: "s", status: s, total_tests: null, events, seq: events.length }) as unknown as Snapshot;

describe("judgeReducer", () => {
  it("drops events at or below the last applied seq", () => {
    const s0 = fromSnapshot(snapshot([status(1, "EXPANDING"), status(2, "RUNNING", 2)]));
    const s1 = judgeReducer(s0, { type: "events", events: [status(2, "RUNNING", 2), test(3, 1, "PASS")] });
    expect(s1.events.map((e) => e.seq)).toEqual([1, 2, 3]);
  });

  it("asks for a resync on a gap in seq", () => {
    const s0 = fromSnapshot(snapshot([status(1, "EXPANDING")]));
    expect(judgeReducer(s0, { type: "events", events: [test(3, 1, "PASS")] }).resync).toBe(true);
  });

  it("never moves the stage backwards", () => {
    const s0 = fromSnapshot(snapshot([status(1, "RUNNING", 2)]));
    expect(judgeReducer(s0, { type: "events", events: [status(2, "EXPANDING")] }).status).toBe("RUNNING");
  });

  it("counts each test once, by its final attempt", () => {
    const s = fromSnapshot(
      snapshot([status(1, "RUNNING", 2), test(2, 1, "SYSTEM_ERROR", 1), test(3, 1, "PASS", 2), test(4, 2, "FAIL")]),
    );
    expect(summarize(s)).toMatchObject({ passed: 1, done: 2, retries: 1 });
  });
});
