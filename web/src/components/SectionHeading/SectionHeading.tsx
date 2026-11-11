import styles from "./SectionHeading.module.css";

/** `## Task` headings, as in the reference statement pane. */
export function SectionHeading({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <h2 className={styles.h} id={id}>
      <span className={styles.hash} aria-hidden="true">
        ##{" "}
      </span>
      {children}
    </h2>
  );
}
