import type { Stage } from "@/lib/api/types";

import { Spinner } from "../Spinner/Spinner";
import styles from "./PipelineBreadcrumb.module.css";

export const STAGES: Stage[] = ["QUEUED", "EXPANDING", "RUNNING", "AGGREGATING", "COMPLETED"];

type Props = { status: string; done?: number; total?: number | null };

/** QUEUED › EXPANDING › RUNNING n/N › AGGREGATING › COMPLETED. Stages only move forward. */
export function PipelineBreadcrumb({ status, done = 0, total }: Props) {
  const failed = status === "FAILED" || status === "TIMED_OUT";
  const at = failed ? STAGES.indexOf("RUNNING") : Math.max(0, STAGES.indexOf(status as Stage));
  const complete = status === "COMPLETED";
  return (
    <ol className={styles.crumbs} aria-label="judging pipeline">
      {STAGES.map((stage, i) => {
        const isCurrent = i === at && !complete;
        const cls = complete
          ? i === STAGES.length - 1
            ? styles.complete
            : styles.done
          : isCurrent
            ? failed
              ? styles.failed
              : styles.current
            : i < at
              ? styles.done
              : "";
        const label =
          stage === "RUNNING" && isCurrent && total ? `RUNNING ${done}/${total}` : stage;
        return (
          <li key={stage} className={styles.stage} aria-current={isCurrent ? "step" : undefined}>
            <span className={`${styles.chip} ${cls}`}>
              {complete || i < at ? "✓" : isCurrent ? failed ? "✕" : <Spinner /> : "·"}{" "}
              {failed && isCurrent ? status : label}
            </span>
            {i < STAGES.length - 1 && (
              <span className={styles.sep} aria-hidden="true">
                ›
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
