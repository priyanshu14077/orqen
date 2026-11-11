"use client";

import { type RefObject, useLayoutEffect, useRef } from "react";

/**
 * FLIP reorder animation for a list keyed by `data-flip-key`. When the order changes,
 * each row slides from its old position to its new one. Used by the scoreboard, where
 * the server decides rank and the client only animates the move.
 */
export function useFlip(container: RefObject<HTMLElement | null>, order: string) {
  const last = useRef(new Map<string, number>());

  useLayoutEffect(() => {
    const el = container.current;
    if (!el) return;
    const rows = Array.from(el.querySelectorAll<HTMLElement>("[data-flip-key]"));
    const next = new Map<string, number>();
    for (const row of rows) {
      const key = row.dataset.flipKey!;
      const top = row.getBoundingClientRect().top;
      next.set(key, top);
      const before = last.current.get(key);
      if (before !== undefined && before !== top) {
        row.animate(
          [{ transform: `translateY(${before - top}px)` }, { transform: "translateY(0)" }],
          { duration: 420, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" },
        );
      }
    }
    last.current = next;
  }, [container, order]);
}
