import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import styles from "./Field.module.css";

type Wrap = { label: string; hint?: string; children: React.ReactNode };

export function Field({ label, hint, children }: Wrap) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>
        {label} {hint && <span className={styles.hint}>· {hint}</span>}
      </span>
      {children}
    </label>
  );
}

export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={`${styles.control} ${p.className ?? ""}`} />
);

export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={`${styles.control} ${p.className ?? ""}`} />
);

export const TextArea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={`${styles.control} ${p.className ?? ""}`} />
);
