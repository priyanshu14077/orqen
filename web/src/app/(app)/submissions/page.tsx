import type { Metadata } from "next";
import Link from "next/link";

import { Reveal, Spinner } from "@/components";
import type { SubmissionRow } from "@/lib/api/types";
import { relative, score100 } from "@/lib/format";
import { serverNow } from "@/lib/server/clock";
import { gateway } from "@/lib/server/gateway";

import base from "../page.module.css";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "submissions" };

const LIVE = new Set(["QUEUED", "EXPANDING", "RUNNING", "AGGREGATING", "WAITING"]);

/** Your submissions. Sample runs are drawn dashed so they never read as ranked submits. */
export default async function SubmissionsPage() {
  const rows = await gateway<SubmissionRow[]>("/v1/submissions?limit=50");
  const now = serverNow();
  return (
    <div className={base.page}>
      <section className={base.hero}>
        <div>
          <div className={base.kicker}>judge</div>
          <h1 className={base.h1}>Your submissions</h1>
          <div className={base.dim}>newest first · open one to watch its judging log</div>
        </div>
      </section>
      <div role="table" aria-label="submissions">
        <div className={styles.head} role="row">
          <span role="columnheader">when</span>
          <span role="columnheader">problem</span>
          <span role="columnheader">mode</span>
          <span role="columnheader">status</span>
          <span role="columnheader" className={styles.right}>score</span>
          <span role="columnheader" className={`${styles.right} ${styles.wide}`}>tests</span>
        </div>
        {rows.map((r, i) => (
          <Reveal key={r.submission_id} delayMs={Math.min(i, 12) * 30}>
            <Link href={`/s/${r.submission_id}`} className={styles.row} role="row">
              <span role="cell" className={styles.dim}>{relative(r.created_at, now)}</span>
              <span role="cell">{r.problem_title}</span>
              <span role="cell">
                <span className={r.mode === "run" ? styles.run : styles.submit}>{r.mode}</span>
              </span>
              <span role="cell" className={styles.status} data-status={r.status}>
                {LIVE.has(r.status) && <Spinner />} {r.status}
              </span>
              <span role="cell" className={styles.score}>{score100(r.score)}</span>
              <span role="cell" className={`${styles.right} ${styles.dim} ${styles.wide}`}>{r.total_tests ?? "—"}</span>
            </Link>
          </Reveal>
        ))}
        {rows.length === 0 && (
          <div className={styles.empty}>
            Nothing yet. <Link href="/">Pick a problem</Link> and run its samples.
          </div>
        )}
      </div>
    </div>
  );
}
