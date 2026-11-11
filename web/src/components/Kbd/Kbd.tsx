import styles from "./Kbd.module.css";

/** A keyboard hint in the terminal style: [e], ctrl+⏎. Hidden from screen readers. */
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <span className={styles.kbd} aria-hidden="true">
      {children}
    </span>
  );
}
