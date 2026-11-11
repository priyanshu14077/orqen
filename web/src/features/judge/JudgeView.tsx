"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  Button,
  CountUp,
  Kbd,
  LiveRegion,
  LogHeader,
  LogRow,
  MetaRow,
  PipelineBreadcrumb,
  StatusBar,
  VerdictLabel,
} from "@/components";
import { useInterval } from "@/hooks/useInterval";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import type { Snapshot, TestEvent, Verdict } from "@/lib/api/types";
import { compactTokens, int, VERDICTS } from "@/lib/format";

import styles from "./JudgeView.module.css";
import { isTerminal, summarize } from "./reducer";
import { useSubmissionStream } from "./useSubmissionStream";

type Props = { snapshot: Snapshot; handle: string };

const REPLAY_MS = 140;

/** Live judging (route /s/:id): breadcrumb, append-only log, summary, status bar. */
export function JudgeView({ snapshot, handle }: Props) {
  const state = useSubmissionStream(snapshot);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [replay, setReplay] = useState<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const events = replay === null ? state.events : state.events.slice(0, replay);
  const stick = useStickToBottom(logRef, events.length);
  useInterval(
    () => setReplay((n) => (n === null || n >= state.events.length ? null : n + 1)),
    replay === null ? null : REPLAY_MS,
  );

  const sum = summarize({ ...state, events });
  const status = replay === null ? state.status : events.reduce((s, e) => (e.type === "status" ? e.status : s), "QUEUED");
  const done = replay === null && isTerminal(state.status);
  const completed = replay === null ? state.completed : null;

  const tests = events.filter((e): e is TestEvent => e.type === "test");
  const meta = events.filter((e) => e.type === "meta");
  const expandable = tests.filter((t) => t.steps > 0);
  const allOpen = expandable.length > 0 && expandable.every((t) => open[t.seq]);

  const toggleAll = () => {
    stick.release();
    setOpen(Object.fromEntries(expandable.map((t) => [t.seq, !allOpen])));
  };
  const startReplay = () => {
    setOpen({});
    setReplay(0);
    stick.stick();
  };

  // [e] expand all, [r] replay. The listener reads the latest handlers through a ref.
  const keys = useRef({ toggleAll, startReplay, done });
  useEffect(() => {
    keys.current = { toggleAll, startReplay, done };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey) return;
      if (e.key === "e") keys.current.toggleAll();
      if (e.key === "r" && keys.current.done) keys.current.startReplay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const first = events[0]?.ts;
  const last = completed?.ts ?? events.at(-1)?.ts;
  const [now, setNow] = useState(() => Date.now());
  useInterval(() => setNow(Date.now()), done ? null : 1000);
  const elapsedS = first ? ((done && last ? new Date(last).getTime() : now) - new Date(first).getTime()) / 1000 : 0;

  const tone = status === "COMPLETED" ? "done" : status === "FAILED" || status === "TIMED_OUT" ? "failed" : status === "RUNNING" ? "running" : "idle";
  const total = state.total ?? snapshot.total_tests ?? 0;
  const score = completed?.score ?? snapshot.score ?? 0;

  return (
    <div className={styles.view}>
      <LiveRegion message={done ? `judging ${status.toLowerCase()}, score ${score.toFixed(1)} of 100` : `stage ${status.toLowerCase()}`} />
      <div className={styles.meta}>
        <h1 className={styles.title}>submission {snapshot.submission_id.slice(0, 8)}</h1>
        <span>
          <Link href={`/p/${snapshot.problem_id}/submit`}>{snapshot.problem_title}</Link>
        </span>
        <span>
          by <span style={{ color: "var(--accent)" }}>{handle}</span>
        </span>
        <span>
          mode <span className={styles.v}>{snapshot.mode}</span>
        </span>
        {snapshot.model && (
          <span>
            model <span className={styles.v}>{snapshot.model}</span>
          </span>
        )}
        <span>
          prompt <span className={styles.v}>{(snapshot.prompt_chars / 1000).toFixed(1)} kB</span>
        </span>
        <span className={styles.fill} />
        <div className={styles.actions}>
          <Button onClick={toggleAll} disabled={expandable.length === 0}>
            <Kbd>[e]</Kbd> {allOpen ? "collapse all" : "expand all"}
          </Button>
          <Button onClick={startReplay} disabled={!done}>
            <Kbd>[r]</Kbd> replay
          </Button>
        </div>
      </div>

      <div className={styles.pipeline}>
        <PipelineBreadcrumb status={status} done={sum.done} total={total} />
        <span className={styles.fill} />
        <span style={{ color: "var(--fg-dim)" }}>
          elapsed <span className={styles.v}>{String(Math.floor(elapsedS / 60)).padStart(2, "0")}:{String(Math.floor(elapsedS % 60)).padStart(2, "0")}</span>
        </span>
      </div>

      <LogHeader />
      <div className={styles.logWrap}>
        <div
          ref={logRef}
          className={styles.log}
          onScroll={stick.onScroll}
          role="log"
          aria-label="judging log"
          aria-busy={!done}
        >
          {meta.map((m) => m.type === "meta" && <MetaRow key={m.seq} ts={m.ts} text={m.text} />)}
          {tests.length === 0 && !done && <div className={styles.empty}>waiting for the first test…</div>}
          {tests.map((t) => (
            <LogRow
              key={t.seq}
              event={t}
              expanded={Boolean(open[t.seq])}
              onToggle={() => {
                stick.release();
                setOpen((o) => ({ ...o, [t.seq]: !o[t.seq] }));
              }}
            />
          ))}
          {completed && (
            <div className={styles.summary}>
              <span className={styles.final}>
                FINAL <CountUp value={completed.score} decimals={1} /> / 100
              </span>
              <span>
                {VERDICTS.filter((v) => sum.counts[v]).map((v, i) => (
                  <span key={v}>
                    {i > 0 && " · "}
                    {sum.counts[v]} <VerdictLabel verdict={v as Verdict} />
                  </span>
                ))}
              </span>
              <span>
                tokens <span className={styles.v}>{int(completed.tokens)}</span>
              </span>
              <span>
                sys retries <span className={styles.v}>{sum.retries}</span>
              </span>
            </div>
          )}
          {done && !completed && state.status !== "COMPLETED" && (
            <div className={styles.empty}>judging ended: {state.status.toLowerCase()}</div>
          )}
        </div>
        {!stick.following && stick.unseen > 0 && (
          <button type="button" className={styles.jump} onClick={stick.stick}>
            ↓ {stick.unseen} new
          </button>
        )}
      </div>

      <StatusBar
        mode={replay !== null ? "REPLAY" : status}
        tone={replay !== null ? "idle" : tone}
        left={[
          { content: `sub/${snapshot.submission_id.slice(0, 8)}`, strong: true },
          { content: snapshot.problem_slug },
        ]}
        right={[
          {
            content: (
              <>
                <span>
                  score <span style={{ color: "var(--fg-bright)" }}>{completed ? completed.score.toFixed(1) : "—"}</span>/100
                </span>
                <span>
                  passed <span style={{ color: "var(--verdict-pass)" }}>{sum.passed}</span>/{total || "—"}
                </span>
                <span>
                  tok <span style={{ color: "var(--fg)" }}>{compactTokens(sum.tokens)}</span>
                </span>
              </>
            ),
          },
          { content: `seq ${String(state.seq).padStart(6, "0")}`, strong: true },
          { content: `ln ${tests.length}/${total || "—"}` },
        ]}
      />
    </div>
  );
}
