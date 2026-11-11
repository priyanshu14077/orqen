"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A polite screen-reader announcer, throttled to one message every `minGapMs`
 * (docs/frontend §10): stage changes and final scores, never individual rows.
 */
export function LiveRegion({ message, minGapMs = 3000 }: { message: string; minGapMs?: number }) {
  const [said, setSaid] = useState("");
  const last = useRef(0);
  useEffect(() => {
    const wait = Math.max(0, last.current + minGapMs - Date.now());
    const t = setTimeout(() => {
      last.current = Date.now();
      setSaid(message);
    }, wait);
    return () => clearTimeout(t);
  }, [message, minGapMs]);
  return (
    <div className="sr-only" aria-live="polite" aria-atomic="true">
      {said}
    </div>
  );
}
