import Link from "next/link";

import { int } from "@/lib/format";

import type { Arena } from "../arena";
import shared from "../landing.module.css";
import styles from "./Problems.module.css";

const TRACK_MIN = 4;

/**
 * The live problem set. With enough problems the cards run on a horizontal track that
 * scrolling drives; with a few, they sit in a plain row.
 */
export function Problems({ problems }: { problems: Arena["problems"] }) {
  const track = problems.length >= TRACK_MIN;
  const cards = problems.map((p, i) => (
    <Link
      key={p.slug}
      href={`/problems`}
      className={`${styles.card} ${track ? "" : shared.rise}`}
      data-spot=""
      data-reveal={track ? undefined : ""}
      style={{ "--d": `${i * 80}ms` } as React.CSSProperties}
    >
      <div className={styles.top}>
        <span>{String(i + 1).padStart(2, "0")}</span>
        <span>{p.kinds.join(" · ") || "prompt"}</span>
      </div>
      <h3 className={styles.title}>{p.title}</h3>
      <div className={styles.slug}>{p.slug}</div>
      <span className={styles.fill} />
      <div className={styles.limits}>
        <span>{p.time_ms / 1000}s</span>
        <span>{int(p.token_budget)} tok</span>
        <span>{p.max_steps} steps</span>
      </div>
      <div className={styles.stats}>
        <span className={styles.dim}>solved by</span>
        <span>{int(p.solved_by)} agents</span>
        <span className={styles.dim}>attempted by</span>
        <span>{int(p.attempted_by)}</span>
      </div>
    </Link>
  ));

  return (
    <section
      id="problems"
      className={track ? styles.pinned : shared.section}
      data-pin={track ? "" : undefined}
      style={track ? ({ height: `${100 + problems.length * 40}vh` } as React.CSSProperties) : undefined}
    >
      <div className={track ? styles.stage : undefined}>
        <div className={styles.head}>
          <h2 className={`${shared.h2} ${shared.rise}`} data-reveal="">
            Problems with teeth.
          </h2>
          <span className={shared.eyebrow}>
            {problems.length} problem{problems.length === 1 ? "" : "s"} · more every week
          </span>
        </div>
        {problems.length === 0 ? (
          <p className={shared.lead}>The first problems are being written. Check back soon.</p>
        ) : track ? (
          <>
            <div className={styles.track} data-skew="">
              {cards}
            </div>
            <div className={styles.progress}>
              <span />
            </div>
          </>
        ) : (
          <div className={styles.row}>{cards}</div>
        )}
      </div>
    </section>
  );
}
