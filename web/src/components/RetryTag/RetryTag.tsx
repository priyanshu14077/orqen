import styles from "./RetryTag.module.css";

/** Marks an infrastructure retry: "retry 1/3". */
export function RetryTag({ attempt, max }: { attempt: number; max: number }) {
  return <span className={styles.tag}>retry {attempt}/{max}</span>;
}
