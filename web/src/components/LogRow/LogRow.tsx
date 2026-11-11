"use client";

import type { TestEvent } from "@/lib/api/types";
import { clockTime, int, redactedWidths, seconds } from "@/lib/format";

import { RetryTag } from "../RetryTag/RetryTag";
import { VerdictLabel } from "../VerdictLabel/VerdictLabel";
import styles from "./LogRow.module.css";

export type ToolCall = {
  step: number;
  tMs: number;
  call: string;
  result: string;
  tokens: number;
  failed: boolean;
};

/** Column headings that line up with `LogRow`. */
export function LogHeader() {
  return (
    <div className={styles.head} aria-hidden="true">
      <span />
      <span>time</span>
      <span>test</span>
      <span>kind</span>
      <span>verdict</span>
      <span className={styles.right}>tokens</span>
      <span className={`${styles.right} ${styles.hideNarrow}`}>steps</span>
      <span className={`${styles.right} ${styles.hideNarrow}`}>latency</span>
      <span>detail</span>
    </div>
  );
}

/** A preamble or epilogue line: `14:02:07.600  expand 8 tests …`. */
export function MetaRow({ ts, text }: { ts: string; text: string }) {
  return (
    <div className={styles.meta}>
      <span />
      <span>{clockTime(ts)}</span>
      <span>{text}</span>
    </div>
  );
}

type Props = {
  event: TestEvent;
  expanded: boolean;
  onToggle: () => void;
  calls?: ToolCall[];
  live?: boolean;
};

/**
 * One judging event. A SYSTEM_ERROR retry is its own dim, non-expandable row; the
 * re-run arrives later as another row. Samples expand to their tool calls; hidden
 * tests expand to redacted bars, drawn from the step count alone.
 */
export function LogRow({ event, expanded, onToggle, calls, live = false }: Props) {
  const system = event.verdict === "SYSTEM_ERROR" && (event.attempt ?? 1) < (event.max_attempts ?? 1);
  const sample = event.kind === "sample";
  const expandable = !system && event.steps > 0;
  const retry =
    event.verdict === "SYSTEM_ERROR" && event.attempt
      ? { attempt: event.attempt, max: event.max_attempts ?? event.attempt }
      : event.attempt && event.attempt > 1
        ? { attempt: event.attempt, max: event.max_attempts ?? event.attempt }
        : null;
  return (
    <div className={styles.item}>
      <button
        type="button"
        className={styles.row}
        data-running={live}
        data-system={system}
        onClick={expandable ? onToggle : undefined}
        disabled={!expandable}
        aria-expanded={expandable ? expanded : undefined}
        aria-label={`test ${event.test}, ${event.kind}, ${event.verdict}`}
      >
        <span className={styles.caret} data-open={expanded} aria-hidden="true">
          {expandable ? "▸" : " "}
        </span>
        <span className={styles.ts}>{live ? "" : clockTime(event.ts)}</span>
        <span className={styles.num}>#{String(event.test).padStart(2, "0")}</span>
        <span className={styles.kind} data-kind={event.kind}>
          {event.kind}
        </span>
        <VerdictLabel verdict={live ? null : event.verdict} animate />
        <span className={`${styles.right} ${event.verdict === "BUDGET" ? styles.budget : ""}`}>
          {live ? "…" : int(event.tokens)}
        </span>
        <span className={`${styles.right} ${styles.hideNarrow}`}>{live ? "…" : event.steps}</span>
        <span className={`${styles.right} ${styles.hideNarrow}`}>{seconds(event.latency_ms)}</span>
        <span className={styles.detail}>
          {retry && <RetryTag attempt={retry.attempt} max={retry.max} />}
          <span className={styles.note}>{event.detail}</span>
        </span>
      </button>
      {expanded && expandable && sample && <TraceList calls={calls ?? []} live={live} steps={event.steps} />}
      {expanded && expandable && !sample && <RedactedTrace test={event.test} steps={event.steps} />}
    </div>
  );
}

/** A sample test's tool calls. M1 problems have no tools, so this may list none. */
export function TraceList({ calls, live, steps }: { calls: ToolCall[]; live: boolean; steps: number }) {
  return (
    <div className={styles.expand}>
      {calls.map((c) => (
        <div key={c.step} className={styles.call}>
          <span className={styles.callN}>{String(c.step).padStart(2, "0")}</span>
          <span className={styles.callT}>+{(c.tMs / 1000).toFixed(1)}s</span>
          <span className={styles.callName}>{c.call}</span>
          <span className={styles.callRes} data-failed={c.failed}>
            → {c.result}
          </span>
          <span className={`${styles.right} ${styles.callT}`}>{(c.tokens / 1000).toFixed(1)}k</span>
        </div>
      ))}
      {calls.length === 0 && !live && (
        <div className={styles.redactNote}>
          {steps} model {steps === 1 ? "call" : "calls"} · no tool calls on this problem
        </div>
      )}
      {live && (
        <div className={styles.thinking}>
          <span style={{ width: 24 }} />
          <span className={styles.cursor}>▍</span>
          <span>agent thinking</span>
        </div>
      )}
    </div>
  );
}

/** Placeholder bars for a hidden test. Widths are seeded by test number so they never shimmer. */
export function RedactedTrace({ test, steps }: { test: number; steps: number }) {
  const widths = redactedWidths(test, steps);
  return (
    <div className={`${styles.expand} ${styles.bars}`}>
      {widths.map((w, j) => (
        <div key={j} className={styles.bar}>
          <span className={styles.callN}>{String(j + 1).padStart(2, "0")}</span>
          <span className={styles.barTime} />
          <span className={styles.barFill} style={{ width: `${w}%`, animationDelay: `${j * 50}ms` }} />
        </div>
      ))}
      <div className={styles.redactNote}>
        {steps} {steps === 1 ? "step" : "steps"} · trace redacted (hidden test)
        {steps > widths.length ? ` · ${steps - widths.length} more` : ""}
      </div>
    </div>
  );
}
