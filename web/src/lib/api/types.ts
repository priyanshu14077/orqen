/** Types generated from the gateway's OpenAPI schema (`npm run types`). */
import type { components } from "./schema";

type S = components["schemas"];

export type Me = S["MeOut"];
export type ProblemSummary = S["ProblemSummary"];
export type Problem = S["Problem"];
export type Standing = S["Standing"];
export type SubmissionRow = S["SubmissionRow"];
export type Snapshot = S["Snapshot"];
export type SubmissionAccepted = S["SubmissionAccepted"];
export type SubmissionIn = S["SubmissionIn"];

export type Verdict = "PASS" | "FAIL" | "TLE" | "MLE" | "ERROR" | "BUDGET" | "SYSTEM_ERROR";
export type Stage = "QUEUED" | "EXPANDING" | "RUNNING" | "AGGREGATING" | "COMPLETED";
export type TerminalStatus = "COMPLETED" | "FAILED" | "TIMED_OUT";

/** Live judging events, as `orqen_gateway.live.ALLOWED` lets them through. */
type Base = { seq: number; ts: string; submission_id: string };
export type MetaEvent = Base & { type: "meta"; text: string };
export type StatusEvent = Base & { type: "status"; status: string; total?: number };
export type TestEvent = Base & {
  type: "test";
  test: number;
  test_case_id: string;
  kind: "sample" | "hidden";
  attempt?: number;
  max_attempts?: number;
  verdict: Verdict;
  score: number | null;
  tokens: number;
  steps: number;
  latency_ms: number | null;
  detail?: string;
};
export type CompletedEvent = Base & {
  type: "completed";
  status: string;
  score: number;
  passed: number;
  total: number;
  tokens: number;
};
export type JudgeEvent = MetaEvent | StatusEvent | TestEvent | CompletedEvent;
