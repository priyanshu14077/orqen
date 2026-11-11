"use client";

import styles from "./SegmentedToggle.module.css";

type Option<T extends string> = { value: T; label: string; disabled?: boolean };

type Props<T extends string> = {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  tone?: "solid" | "soft";
  size?: "sm" | "lg";
};

/** A radio group drawn as joined square buttons (editor tabs, live/final, judge type). */
export function SegmentedToggle<T extends string>({
  label,
  options,
  value,
  onChange,
  tone = "solid",
  size = "sm",
}: Props<T>) {
  const move = (dir: 1 | -1) => {
    const enabled = options.filter((o) => !o.disabled);
    const i = enabled.findIndex((o) => o.value === value);
    onChange(enabled[(i + dir + enabled.length) % enabled.length].value);
  };
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`${styles.group} ${tone === "soft" ? styles.soft : ""} ${size === "lg" ? styles.lg : ""}`}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") move(1);
        if (e.key === "ArrowLeft") move(-1);
      }}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          disabled={o.disabled}
          className={styles.option}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
