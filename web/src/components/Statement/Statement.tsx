import { Fragment } from "react";

import styles from "./Statement.module.css";

/**
 * Renders a problem statement: paragraphs, `code` and **bold**. It builds React nodes
 * from the text and never injects HTML, so a statement can't carry markup or scripts.
 */
export function Statement({ markdown }: { markdown: string }) {
  const paragraphs = markdown
    .trim()
    .split(/\n{2,}/)
    .map((p) => p.replace(/\n/g, " "));
  return (
    <div className={styles.prose}>
      {paragraphs.map((p, i) => (
        <p key={i}>{inline(p)}</p>
      ))}
    </div>
  );
}

function inline(text: string): React.ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className={styles.code}>
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className={styles.strong}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
