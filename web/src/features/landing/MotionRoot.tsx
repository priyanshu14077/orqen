"use client";

import { useEffect, useRef } from "react";

import { mountMotion, MOTION_SELECTOR } from "./motion";

/**
 * Wires the landing page's data-attribute effects to everything inside it, and wires
 * them again when streamed sections arrive (the live log's own updates don't count).
 */
export function MotionRoot({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    let stop = mountMotion(el, query.matches);
    let pending = 0;
    const change = () => {
      pending = 0;
      stop();
      stop = mountMotion(el, query.matches);
    };
    const streamed = new MutationObserver((records) => {
      const added = records.some((r) =>
        Array.from(r.addedNodes).some(
          (n) => n instanceof Element && (n.matches(MOTION_SELECTOR) || n.querySelector(MOTION_SELECTOR)),
        ),
      );
      if (added && !pending) pending = requestAnimationFrame(change);
    });
    streamed.observe(el, { childList: true, subtree: true });
    query.addEventListener("change", change);
    return () => {
      streamed.disconnect();
      cancelAnimationFrame(pending);
      query.removeEventListener("change", change);
      stop();
    };
  }, []);
  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
