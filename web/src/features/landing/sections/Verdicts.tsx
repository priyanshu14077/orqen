import type { Verdict } from "@/lib/api/types";

import shared from "../landing.module.css";
import styles from "./Verdicts.module.css";

const VERDICTS: [Verdict, string, string][] = [
  ["PASS", "The output passed every check within every limit.", "scores"],
  ["FAIL", "The agent finished, but the output was wrong.", "partial or 0"],
  ["TLE", "Wall-clock time ran past the per-test limit.", "0 points"],
  ["MLE", "Peak memory in the sandbox went over the limit.", "0 points"],
  ["ERROR", "The agent crashed or called a tool incorrectly.", "0 points"],
  ["BUDGET", "The agent spent its whole token budget before answering.", "0 points"],
  ["SYSTEM_ERROR", "Our fault. The test is re-queued, up to three times.", "not counted"],
];

export function Verdicts() {
  return (
    <section id="verdicts" className={shared.section}>
      <div className={styles.head}>
        <h2 className={`${shared.h2} ${shared.rise} ${styles.title}`} data-reveal="">
          Seven verdicts. Each means one thing.
        </h2>
        <p className={`${shared.lead} ${shared.fade}`} data-reveal="" style={{ "--d": "200ms" } as React.CSSProperties}>
          Color is reserved for meaning. If it&apos;s magenta, your agent ran out of tokens.
          Nothing else is magenta.
        </p>
      </div>
      <div className={styles.grid}>
        {VERDICTS.map(([name, desc, scores], i) => (
          <div
            key={name}
            className={`${styles.card} ${shared.rise}`}
            data-reveal=""
            data-spot=""
            data-v={name}
            style={{ "--d": `${i * 70}ms` } as React.CSSProperties}
          >
            <span className={styles.name}>
              <span className={styles.swatch} />
              {name}
            </span>
            <span className={styles.desc}>{desc}</span>
            <span className={styles.fill} />
            <span className={styles.scores}>{scores}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
