"use client";

import { useRef } from "react";

import { useReveal } from "@/hooks/useReveal";

import styles from "./Reveal.module.css";

type Props = { children: React.ReactNode; delayMs?: number; as?: "div" | "section" | "li" };

/** Fades and lifts its children in the first time they scroll into view. */
export function Reveal({ children, delayMs = 0, as: Tag = "div" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useReveal(ref);
  return (
    <Tag
      ref={ref as React.Ref<never>}
      className={styles.reveal}
      data-seen={seen}
      style={{ transitionDelay: `${delayMs}ms` }}
    >
      {children}
    </Tag>
  );
}
