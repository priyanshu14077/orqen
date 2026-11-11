import styles from "./StatusBar.module.css";

type Segment = { content: React.ReactNode; strong?: boolean };

type Props = {
  mode: string;
  tone?: "idle" | "running" | "done" | "failed";
  left?: Segment[];
  right?: Segment[];
};

/** The vim-style bar under the log: `-- RUNNING --` sub/… score … seq. */
export function StatusBar({ mode, tone = "idle", left = [], right = [] }: Props) {
  const seg = (s: Segment, i: number) => (
    <span key={i} className={`${styles.seg} ${s.strong ? styles.strong : ""}`}>
      {s.content}
    </span>
  );
  return (
    <div className={styles.bar} role="status" aria-live="off">
      <span className={styles.mode} data-tone={tone}>
        -- {mode} --
      </span>
      {left.map(seg)}
      <span className={styles.fill} />
      {right.map(seg)}
    </div>
  );
}
