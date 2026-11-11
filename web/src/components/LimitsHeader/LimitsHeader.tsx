import { int } from "@/lib/format";

import styles from "./LimitsHeader.module.css";

export type LimitsProps = {
  timeMs: number;
  memoryMb: number;
  tokenBudget: number;
  maxSteps: number;
  models: string[];
  temperature?: string;
};

/** The six-cell limits grid at the top of a problem. */
export function LimitsHeader(p: LimitsProps) {
  const cells: [string, string][] = [
    ["time", `${p.timeMs / 1000} s / test`],
    ["memory", `${p.memoryMb} MB`],
    ["token budget", `${int(p.tokenBudget)} / test`],
    ["max steps", String(p.maxSteps)],
    ["models", p.models.join(" · ")],
    ["temperature", p.temperature ?? "0.0 fixed"],
  ];
  return (
    <dl className={styles.grid}>
      {cells.map(([label, value], i) => (
        <div key={label} className={styles.cell} style={{ animationDelay: `${i * 40}ms` }}>
          <dt className={styles.label}>{label}</dt>
          <dd className={styles.value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
