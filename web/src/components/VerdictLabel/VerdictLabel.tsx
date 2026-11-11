import type { Verdict } from "@/lib/api/types";
import { VERDICT_TOKEN } from "@/lib/format";

import { Spinner } from "../Spinner/Spinner";
import styles from "./VerdictLabel.module.css";

type Props = { verdict: Verdict | null; animate?: boolean };

/** A verdict in its token colour, always with its label (colour is never the only cue). */
export function VerdictLabel({ verdict, animate = false }: Props) {
  if (!verdict) {
    return (
      <span className={`${styles.verdict} ${styles.running}`}>
        RUNNING <Spinner label="running" />
      </span>
    );
  }
  return (
    <span
      className={`${styles.verdict} ${animate ? styles.landed : ""}`}
      style={{ color: VERDICT_TOKEN[verdict] }}
      data-verdict={verdict}
    >
      {verdict}
    </span>
  );
}
