"use client";

import { useState } from "react";

import styles from "./CodeEditor.module.css";

type Props = {
  value: string;
  onChange: (value: string) => void;
  label: string;
  onSubmit?: () => void;
  disabled?: boolean;
};

/**
 * A plain textarea with a line-number gutter. The textarea grows with its content, so
 * the surrounding pane scrolls gutter and text together. Tab inserts four spaces;
 * ctrl/⌘+Enter calls `onSubmit`.
 */
export function CodeEditor({ value, onChange, label, onSubmit, disabled }: Props) {
  const [line, setLine] = useState(1);
  const lines = value.split("\n").length;
  const track = (el: HTMLTextAreaElement) =>
    setLine(el.value.slice(0, el.selectionStart).split("\n").length);
  return (
    <div className={styles.editor}>
      <div className={styles.gutter} aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className={styles.ln} data-current={i + 1 === line}>
            {i + 1}
          </div>
        ))}
      </div>
      <textarea
        aria-label={label}
        className={styles.text}
        value={value}
        disabled={disabled}
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        style={{ height: lines * 20 + 20 }}
        onChange={(e) => {
          onChange(e.target.value);
          track(e.target);
        }}
        onSelect={(e) => track(e.currentTarget)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            onSubmit?.();
          } else if (e.key === "Tab" && !e.shiftKey) {
            e.preventDefault();
            const el = e.currentTarget;
            const { selectionStart: s, selectionEnd: end } = el;
            const next = `${value.slice(0, s)}    ${value.slice(end)}`;
            onChange(next);
            requestAnimationFrame(() => el.setSelectionRange(s + 4, s + 4));
          }
        }}
      />
    </div>
  );
}
