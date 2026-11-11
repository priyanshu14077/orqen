import styles from "./AgreementMeter.module.css";

type Props = { kappa: number; threshold: number; stale?: boolean; caption?: string };

/** Cohen's κ against the activation threshold, with the threshold drawn as a tick. */
export function AgreementMeter({ kappa, threshold, stale = false, caption }: Props) {
  const color = stale ? "var(--fg-mute)" : kappa >= threshold ? "var(--verdict-pass)" : "var(--verdict-limit)";
  return (
    <div className={styles.wrap}>
      <div className={styles.top}>
        <span>calibration agreement</span>
        <span>vs human labels</span>
      </div>
      <div className={styles.value}>
        <span className={styles.kappa}>κ {kappa.toFixed(2)}</span>
        <span className={styles.req}>required ≥ {threshold.toFixed(2)}</span>
      </div>
      <div
        className={styles.track}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={Number(kappa.toFixed(2))}
        aria-label="calibration agreement"
      >
        <div className={styles.fill} style={{ width: `${(kappa * 100).toFixed(1)}%`, background: color }} />
        <div className={styles.mark} style={{ left: `${threshold * 100}%` }} />
      </div>
      <div className={styles.scale} aria-hidden="true">
        <span>0.00</span>
        <span>0.50</span>
        <span>1.00</span>
      </div>
      {caption && <div className={styles.req}>{caption}</div>}
      {stale && <div className={styles.stale}>rule changed since last run · re-calibrate before activating</div>}
    </div>
  );
}
