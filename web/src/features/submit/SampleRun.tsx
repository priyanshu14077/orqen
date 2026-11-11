"use client";

import Link from "next/link";

import { Spinner, VerdictLabel } from "@/components";
import { latestByTest } from "@/features/judge/reducer";
import { useSubmissionStream } from "@/features/judge/useSubmissionStream";
import type { Snapshot } from "@/lib/api/types";
import { int, seconds } from "@/lib/format";

import styles from "./SubmitView.module.css";

/** Inline results of "Run samples", streamed live from the same pipeline. */
export function SampleRun({ snapshot }: { snapshot: Snapshot }) {
  const state = useSubmissionStream(snapshot);
  const latest = [...latestByTest(state.events).values()].sort((a, b) => a.test - b.test);
  const total = state.total ?? 0;
  const pending = Math.max(0, total - latest.length);
  return (
    <div className={styles.samples} aria-live="polite">
      {latest.map((t) => (
        <div key={t.test} className={styles.sampleRow}>
          <span className={styles.dim}>sample {t.test}</span>
          <VerdictLabel verdict={t.verdict} animate />
          <span>{int(t.tokens)}</span>
          <span>{t.steps}</span>
          <span>{seconds(t.latency_ms)}</span>
        </div>
      ))}
      {Array.from({ length: pending }, (_, i) => (
        <div key={`p${i}`} className={styles.sampleRow}>
          <span className={styles.dim}>sample {latest.length + i + 1}</span>
          <VerdictLabel verdict={null} />
          <span>…</span>
          <span>…</span>
          <span>…</span>
        </div>
      ))}
      {total === 0 && (
        <div className={styles.dim}>
          <Spinner /> {state.status.toLowerCase()}
        </div>
      )}
      <div className={styles.dim}>
        sample run · not ranked · <Link href={`/s/${snapshot.submission_id}`}>open log</Link>
      </div>
    </div>
  );
}
