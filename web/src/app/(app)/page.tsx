import type { Metadata } from "next";
import Link from "next/link";

import { Reveal } from "@/components";
import type { ProblemSummary } from "@/lib/api/types";
import { int, score100 } from "@/lib/format";
import { gateway } from "@/lib/server/gateway";
import { getMe } from "@/lib/server/viewer";

import styles from "./page.module.css";

export const metadata: Metadata = { title: "problems" };

export default async function ProblemsPage() {
  const [me, problems] = await Promise.all([getMe(), gateway<ProblemSummary[]>("/v1/problems")]);
  const solved = problems.filter((p) => (p.my_best ?? 0) >= 100).length;
  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div>
          <div className={styles.kicker}>practice archive</div>
          <h1 className={styles.h1}>Problems</h1>
          <div className={styles.dim}>
            signed in as {me.handle} · {me.plan_id?.replace("_", " ") ?? "no plan"} ·{" "}
            {me.subscription_status ?? "inactive"}
          </div>
        </div>
        <span className={styles.fill} />
        <div className={styles.stat}>
          <div className={styles.kicker}>solved</div>
          <div className={styles.statN}>
            {solved}
            <span className={styles.dim}>/{problems.length}</span>
          </div>
        </div>
      </section>
      <div role="table" aria-label="problems">
        <div className={styles.head} role="row">
          <span role="columnheader">#</span>
          <span role="columnheader">problem</span>
          <span role="columnheader" className={styles.wide}>models</span>
          <span role="columnheader" className={`${styles.right} ${styles.wide}`}>budget</span>
          <span role="columnheader" className={`${styles.right} ${styles.wide}`}>time</span>
          <span role="columnheader" className={styles.right}>best</span>
          <span role="columnheader" className={styles.right}>solved by</span>
        </div>
        {problems.map((p, i) => (
          <Reveal key={p.problem_id} delayMs={i * 50}>
            <Link href={`/p/${p.problem_id}/submit`} className={styles.row} role="row">
              <span className={styles.dim} role="cell">{String(i + 1).padStart(2, "0")}</span>
              <span role="cell">
                <span className={styles.title}>{p.title}</span>
                <span className={styles.slug}>{p.slug}</span>
              </span>
              <span role="cell" className={`${styles.dim} ${styles.wide}`}>{p.limits.models.join(" · ")}</span>
              <span role="cell" className={`${styles.right} ${styles.wide}`}>{int(p.limits.token_budget)}</span>
              <span role="cell" className={`${styles.right} ${styles.wide}`}>{p.limits.time_ms / 1000}s</span>
              <span role="cell" className={`${styles.best} ${(p.my_best ?? 0) >= 100 ? styles.solved : ""}`}>
                {score100(p.my_best)}
              </span>
              <span role="cell" className={`${styles.right} ${styles.dim}`}>{p.solved_by}</span>
            </Link>
          </Reveal>
        ))}
      </div>
      <div className={styles.foot}>
        {problems.length === 0 ? "No problems are open yet." : "Pick a problem, write a prompt, run the samples, then submit."}
      </div>
    </div>
  );
}
