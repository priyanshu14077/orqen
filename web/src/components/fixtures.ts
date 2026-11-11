import type { TestEvent, Verdict } from "@/lib/api/types";

/** Fixtures for the component workbench: one per verdict and stage (docs/frontend §9). */
export function testEvent(over: Partial<TestEvent> & { test: number; verdict: Verdict }): TestEvent {
  return {
    seq: over.test,
    ts: "2026-11-11T14:02:11.412Z",
    submission_id: "00000000-0000-0000-0000-000000000000",
    type: "test",
    test_case_id: `tc-${over.test}`,
    kind: "hidden",
    attempt: 1,
    max_attempts: 3,
    score: over.verdict === "PASS" ? 1 : 0,
    tokens: 8412,
    steps: 7,
    latency_ms: 41_200,
    detail: "",
    ...over,
  };
}

export const ALL_ROWS: TestEvent[] = [
  testEvent({ test: 1, verdict: "PASS", kind: "sample" }),
  testEvent({ test: 2, verdict: "FAIL", detail: "failed json_fields, numeric_tolerance" }),
  testEvent({ test: 3, verdict: "TLE", tokens: 21088, steps: 23, latency_ms: 120_000, detail: "wall 120.0 s ≥ limit" }),
  testEvent({ test: 4, verdict: "MLE", detail: "peak 531 MB > 512 MB" }),
  testEvent({ test: 5, verdict: "ERROR", detail: "agent exception: KeyError 'diff' at step 6" }),
  testEvent({ test: 6, verdict: "BUDGET", tokens: 60000, steps: 31, detail: "60,000 / 60,000 tok at step 31" }),
  testEvent({ test: 7, verdict: "SYSTEM_ERROR", tokens: 0, steps: 0, latency_ms: 3000, detail: "sandbox OOM-killed by host · re-queued" }),
  testEvent({ test: 7, seq: 8, verdict: "PASS", attempt: 2 }),
];
