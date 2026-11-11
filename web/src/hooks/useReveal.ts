"use client";

import { type RefObject, useEffect, useState } from "react";

/** True once the element has scrolled into view; drives scroll-reveal animations. */
export function useReveal(ref: RefObject<HTMLElement | null>, rootMargin = "0px 0px -8% 0px") {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, rootMargin, seen]);
  return seen;
}
