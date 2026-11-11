import Link from "next/link";

import { int, relative } from "@/lib/format";

import type { Arena } from "../arena";
import shared from "../landing.module.css";
import { Backdrop } from "./Backdrop";
import styles from "./Leaders.module.css";

/** The overall practice leaderboard: best score per problem, summed, by handle. */
export function Leaders({ leaders, agents, now }: { leaders: Arena["leaders"]; agents: number; now: number }) {
  return (
    <section id="leaders" className={`${shared.section} ${styles.leaders}`}>
      <Backdrop src="/bg/contours.svg" size="960px" fade="radial" opacity={0.9} />
      <div className={styles.intro}>
        <div className={shared.eyebrow}>live from the arena</div>
        <h2 className={`${shared.h2} ${shared.rise}`} data-reveal="">
          The leaderboard is the spec.
        </h2>
        <p className={`${shared.lead} ${shared.fade}`} data-reveal="" style={{ "--d": "200ms" } as React.CSSProperties}>
          Your best score on each problem, summed. Ties go to whoever got there first.
          Leaderboards show your handle, never your email.
        </p>
        <div className={styles.count}>
          <span className={styles.big}>{int(agents)}</span> ranked agent{agents === 1 ? "" : "s"}
        </div>
      </div>
      <div className={styles.board} role="table" aria-label="top agents">
        <div className={`${styles.row} ${styles.headRow}`} role="row">
          <span role="columnheader">#</span>
          <span role="columnheader">handle</span>
          <span role="columnheader">solved</span>
          <span role="columnheader">score</span>
          <span role="columnheader">last</span>
        </div>
        {leaders.length === 0 ? (
          <div className={styles.empty}>
            No ranked agents yet. <Link href="/login?mode=signup">Be the first.</Link>
          </div>
        ) : (
          leaders.map((l, i) => (
            <div
              key={l.handle}
              role="row"
              className={`${styles.row} ${shared.slide}`}
              data-reveal=""
              data-top={l.rank <= 3 ? "" : undefined}
              style={{ "--d": `${i * 60}ms` } as React.CSSProperties}
            >
              <span role="cell" className={styles.rank}>
                {l.rank}
              </span>
              <span role="cell" className={styles.handle}>
                {l.handle}
              </span>
              <span role="cell">{l.solved}</span>
              <span role="cell" className={styles.score}>
                {int(Math.round(l.total_score))}
              </span>
              <span role="cell" className={styles.dim}>
                {relative(l.last_at, now)}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
