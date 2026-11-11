"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  Button,
  CodeEditor,
  Handle,
  Kbd,
  LimitsHeader,
  Notice,
  Reveal,
  SectionHeading,
  SegmentedToggle,
  Statement,
} from "@/components";
import { api } from "@/lib/client/api";
import { local } from "@/lib/client/storage";
import type { Problem, Snapshot, Standing, SubmissionAccepted } from "@/lib/api/types";
import { score100 } from "@/lib/format";

import { SampleRun } from "./SampleRun";
import styles from "./SubmitView.module.css";

type Mode = "prompt" | "code";
type Draft = { prompt: string; code: string; model: string };

const STARTER: Omit<Draft, "model"> = {
  prompt:
    "# system prompt\nYou extract structured fields from messy text.\n\nReturn only a JSON object with the keys the task asks for.\nUse ISO 8601 dates and ISO 4217 currency codes.\nNumbers are plain JSON numbers, without separators or symbols.\n",
  code: 'from orqen import Agent\n\nagent = Agent(model="claude-haiku-4-5", temperature=0.0)\n\ndef solve(task):\n    return agent.run(task["text"])\n',
};

const REFUSAL: Record<number, [string, string]> = {
  402: ["402", "your plan has no submissions left: the free trial includes one"],
  429: ["429", "rate limit reached"],
  403: ["403", "your account isn't set up yet; sign out and in again"],
  404: ["404", "this problem isn't open for submissions"],
};

type Props = { problem: Problem; leaderboard: Standing[] };

/** The submission screen (route /p/:id/submit): statement on the left, editor on the right. */
export function SubmitView({ problem, leaderboard }: Props) {
  const router = useRouter();
  const key = `orqen:draft:${problem.problem_id}`;
  const [mode, setMode] = useState<Mode>("prompt");
  const [draft, setDraft] = useState<Draft>({ ...STARTER, model: problem.limits.models[0] });
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);
  const [error, setError] = useState<[string, string] | null>(null);
  const [run, setRun] = useState<Snapshot | null>(null);
  const [progress, setProgress] = useState(0);
  const leftRef = useRef<HTMLDivElement>(null);
  const idem = useRef<string | null>(null);

  // Restore, then autosave the draft locally (the server has no drafts yet).
  useEffect(() => {
    const saved = local.get<Draft>(key);
    // Local storage exists only in the browser, so the saved draft loads after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved) setDraft((d) => ({ ...d, ...saved }));
  }, [key]);
  useEffect(() => {
    const t = setTimeout(() => local.set(key, draft), 400);
    idem.current = null; // an edited draft is a new submission
    return () => clearTimeout(t);
  }, [key, draft]);

  const text = draft[mode];
  const lines = text.split("\n").length;

  const send = useCallback(
    async (kind: "run" | "submit") => {
      if (busy || mode !== "prompt" || !draft.prompt.trim()) return;
      setBusy(kind);
      setError(null);
      idem.current ??= crypto.randomUUID();
      const res = await api<SubmissionAccepted>("v1/submissions", {
        method: "POST",
        idempotencyKey: kind === "submit" ? idem.current : undefined,
        body: { problem_id: problem.problem_id, mode: kind, kind: "prompt", prompt: draft.prompt, model: draft.model },
      });
      if (!res.ok) {
        setError(REFUSAL[res.status] ? [REFUSAL[res.status][0], `${REFUSAL[res.status][1]} · ${res.detail}`] : [String(res.status || "net"), res.detail]);
        setBusy(null);
        return;
      }
      if (kind === "submit") {
        router.push(`/s/${res.data.submission_id}`);
        return;
      }
      const snap = await api<Snapshot>(`v1/submissions/${res.data.submission_id}`);
      if (snap.ok) setRun(snap.data);
      setBusy(null);
    },
    [busy, mode, draft, problem.problem_id, router],
  );

  return (
    <div className={styles.view}>
      <div
        ref={leftRef}
        className={styles.left}
        onScroll={(e) => {
          const el = e.currentTarget;
          setProgress(el.scrollTop / Math.max(1, el.scrollHeight - el.clientHeight));
        }}
      >
        <div className={styles.progress} style={{ transform: `scaleX(${progress})` }} aria-hidden="true" />
        <div className={styles.head}>
          <span className={styles.code}>{problem.slug}</span>
          <h1 className={styles.title}>{problem.title}</h1>
          <span className={styles.fill} />
          <span className={styles.dim}>
            {problem.kinds.join(" · ")} · best {score100(problem.my_best)}
          </span>
        </div>
        <LimitsHeader
          timeMs={problem.limits.time_ms}
          memoryMb={problem.limits.memory_mb}
          tokenBudget={problem.limits.token_budget}
          maxSteps={problem.limits.max_steps}
          models={problem.limits.models}
        />
        <div className={styles.body}>
          <Reveal as="section">
            <SectionHeading>Task</SectionHeading>
            <Statement markdown={problem.statement_md} />
          </Reveal>
          <Reveal as="section">
            <SectionHeading>Scoring</SectionHeading>
            <p style={{ margin: 0 }}>
              Each test scores the share of the eval rule&apos;s checks it passes. The submission
              score is the weighted average, 0 to 100; a test is accepted at {Math.round(problem.pass_mark * 100)}%.
              Exceeding the token budget ends the test with <span style={{ color: "var(--verdict-budget)" }}>BUDGET</span>.
            </p>
          </Reveal>
          {problem.samples.map((s, i) => (
            <Reveal as="section" key={s.ordinal} delayMs={i * 40}>
              <SectionHeading>Sample {s.ordinal}</SectionHeading>
              <div className={styles.box}>
                <div className={styles.boxHead}>
                  <span>input</span>
                </div>
                <pre className={styles.pre}>{JSON.stringify(s.input, null, 2)}</pre>
                <div className={styles.boxHead}>
                  <span>expected</span>
                </div>
                <pre className={styles.pre}>{JSON.stringify(s.expected, null, 2)}</pre>
              </div>
            </Reveal>
          ))}
          <Reveal as="section">
            <SectionHeading>Leaderboard</SectionHeading>
            {leaderboard.length === 0 ? (
              <p style={{ margin: 0 }} className={styles.dim}>
                No accepted submissions yet. Be the first.
              </p>
            ) : (
              <div className={styles.board}>
                {leaderboard.map((r) => (
                  <Row key={r.handle} r={r} />
                ))}
              </div>
            )}
          </Reveal>
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.toolbar}>
          <SegmentedToggle
            label="editor"
            value={mode}
            onChange={setMode}
            options={[
              { value: "prompt", label: "prompt" },
              { value: "code", label: "code" },
            ]}
          />
          <span className={styles.dim}>{mode === "prompt" ? "system.md" : "agent.py"}</span>
          <span className={styles.fill} />
          <label className={styles.dim}>
            model{" "}
            <select
              className={styles.model}
              value={draft.model}
              onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))}
            >
              {problem.limits.models.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
        </div>
        <div className={styles.editor}>
          <CodeEditor
            label={mode === "prompt" ? "system prompt" : "agent code"}
            value={text}
            onChange={(v) => setDraft((d) => ({ ...d, [mode]: v }))}
            onSubmit={() => void send("submit")}
          />
        </div>
        {(error || mode === "code") && (
          <div className={styles.notices}>
            {mode === "code" && (
              <Notice tone="warn" tag="M3">
                agent code runs in the sandbox, which isn&apos;t live yet. Your draft is saved; submit a prompt for now.
              </Notice>
            )}
            {error && (
              <Notice tone="error" tag={error[0]}>
                {error[1]}
              </Notice>
            )}
          </div>
        )}
        {run && <SampleRun key={run.submission_id} snapshot={run} />}
        <div className={styles.footer}>
          <span className={styles.dim}>
            {lines} lines · ≈ {Math.round(text.length / 3.8)} tok
          </span>
          <span className={styles.fill} />
          <Kbd>ctrl+⏎ submit</Kbd>
          <Button variant="outline" size="md" onClick={() => void send("run")} disabled={busy !== null || mode !== "prompt"}>
            {busy === "run" ? "Running…" : "Run samples"}
          </Button>
          <Button variant="primary" size="md" onClick={() => void send("submit")} disabled={busy !== null || mode !== "prompt"}>
            {busy === "submit" ? "Submitting…" : "Submit"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Row({ r }: { r: Standing }) {
  return (
    <>
      <span className={styles.dim}>{r.rank}</span>
      <span>
        <Handle handle={r.handle} you={r.you} />
      </span>
      <span style={{ color: "var(--fg-bright)" }}>{r.best_score.toFixed(1)}</span>
      <span className={styles.dim}>{new Date(r.reached_at).toLocaleDateString("en-GB")}</span>
    </>
  );
}
