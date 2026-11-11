import styles from "./VersionList.module.css";

export type RuleVersion = {
  version: number;
  status: "draft" | "active" | "superseded" | "rejected";
  kappa: number | null;
  author: string;
  sha?: string;
  createdAt: string;
  note: string;
};

const STATUS: Record<RuleVersion["status"], [string, string]> = {
  draft: ["draft", "var(--fg-bright)"],
  active: ["● active", "var(--verdict-pass)"],
  superseded: ["superseded", "var(--fg-dim)"],
  rejected: ["never active", "var(--fg-mute)"],
};

/** Saved rule versions. They're immutable, so there is no edit control on any row. */
export function VersionList({ versions }: { versions: RuleVersion[] }) {
  return (
    <ol className={styles.list}>
      {versions.map((v, i) => {
        const [label, color] = STATUS[v.status];
        return (
          <li key={v.version} className={styles.item} style={{ animationDelay: `${i * 40}ms` }}>
            <div className={styles.line}>
              <span className={styles.v}>v{v.version}</span>
              <span className={styles.status} style={{ color }}>{label}</span>
              <span className={styles.k}>κ {v.kappa == null ? "—" : v.kappa.toFixed(2)}</span>
              <span>{v.author}</span>
              <span className={styles.fill} />
              <span className={styles.sha}>{v.sha ? `⊘ ${v.sha}` : ""}</span>
            </div>
            <div className={styles.note}>
              <span style={{ width: 24 }} />
              <span>
                {v.createdAt} · {v.note}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
