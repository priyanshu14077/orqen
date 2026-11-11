import type { CompletedEvent, JudgeEvent, Snapshot, TestEvent } from "@/lib/api/types";

/**
 * Live judging state. The server is the source of truth; this only orders, dedups and
 * folds what it sends (docs/frontend §4):
 *   - events at or below the last applied `seq` are dropped;
 *   - a gap in `seq` sets `resync`, and the caller refetches the snapshot;
 *   - the stage only moves forward.
 */
export type JudgeState = {
  submissionId: string;
  status: string;
  total: number | null;
  seq: number;
  events: JudgeEvent[];
  completed: CompletedEvent | null;
  resync: boolean;
};

export type JudgeAction =
  | { type: "snapshot"; snapshot: Snapshot }
  | { type: "events"; events: JudgeEvent[] };

const ORDER = ["QUEUED", "EXPANDING", "RUNNING", "AGGREGATING", "COMPLETED"];
const TERMINAL = new Set(["COMPLETED", "FAILED", "TIMED_OUT"]);

export function isTerminal(status: string): boolean {
  return TERMINAL.has(status);
}

function advance(current: string, next: string): string {
  if (isTerminal(current)) return current;
  if (isTerminal(next)) return next;
  return ORDER.indexOf(next) > ORDER.indexOf(current) ? next : current;
}

function fold(base: JudgeState, events: JudgeEvent[]): JudgeState {
  let s = base;
  for (const e of events) {
    if (e.seq <= s.seq) continue;
    if (e.seq > s.seq + 1 && s.seq > 0) return { ...s, resync: true };
    s = { ...s, seq: e.seq, events: [...s.events, e] };
    if (e.type === "status") {
      s = { ...s, status: advance(s.status, e.status), total: e.total ?? s.total };
    } else if (e.type === "completed") {
      s = { ...s, status: advance(s.status, e.status), completed: e, total: e.total };
    }
  }
  return s;
}

export function fromSnapshot(snapshot: Snapshot): JudgeState {
  const events = [...(snapshot.events as JudgeEvent[])].sort((a, b) => a.seq - b.seq);
  const base: JudgeState = {
    submissionId: snapshot.submission_id,
    status: snapshot.status,
    total: snapshot.total_tests ?? null,
    seq: 0,
    events: [],
    completed: null,
    resync: false,
  };
  // A snapshot rebuilt from stored results may not start at seq 1; accept it whole.
  const folded = fold({ ...base, seq: (events[0]?.seq ?? 1) - 1 }, events);
  return { ...folded, status: advance(folded.status, snapshot.status), resync: false };
}

export function judgeReducer(state: JudgeState, action: JudgeAction): JudgeState {
  if (action.type === "snapshot") return fromSnapshot(action.snapshot);
  const sorted = [...action.events].sort((a, b) => a.seq - b.seq);
  return fold(state, sorted);
}

/** Each test once, by its latest event: retried tests count their final attempt. */
export function latestByTest(events: JudgeEvent[]): Map<number, TestEvent> {
  const latest = new Map<number, TestEvent>();
  for (const e of events) if (e.type === "test") latest.set(e.test, e);
  return latest;
}

export function summarize(state: JudgeState) {
  const latest = latestByTest(state.events);
  let passed = 0;
  let tokens = 0;
  const counts: Record<string, number> = {};
  for (const t of latest.values()) {
    if (t.verdict === "PASS") passed += 1;
    counts[t.verdict] = (counts[t.verdict] ?? 0) + 1;
  }
  for (const e of state.events) if (e.type === "test") tokens += e.tokens;
  const retries = state.events.filter(
    (e) => e.type === "test" && e.verdict === "SYSTEM_ERROR" && (e.attempt ?? 1) < (e.max_attempts ?? 1),
  ).length;
  return { passed, done: latest.size, tokens, counts, retries };
}
