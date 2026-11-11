import styles from "./Notice.module.css";

type Props = { tone?: "error" | "warn" | "info" | "preview"; tag: string; children: React.ReactNode };

/** An inline message: `[402] your trial includes one submission …`. */
export function Notice({ tone = "info", tag, children }: Props) {
  return (
    <div className={`${styles.notice} ${styles[tone]}`} role={tone === "error" ? "alert" : "note"}>
      <span className={styles.tag}>[{tag}]</span>
      <span>{children}</span>
    </div>
  );
}
