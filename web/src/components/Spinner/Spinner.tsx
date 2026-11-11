"use client";

import { useState } from "react";

import { useInterval } from "@/hooks/useInterval";
import { useReducedMotion } from "@/hooks/useReducedMotion";

const FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";

/** The braille spinner the reference build uses for "in progress". */
export function Spinner({ label = "in progress" }: { label?: string }) {
  const reduced = useReducedMotion();
  const [i, setI] = useState(0);
  useInterval(() => setI((n) => (n + 1) % FRAMES.length), reduced ? null : 80);
  return (
    <span role="img" aria-label={label}>
      {reduced ? "⠿" : FRAMES[i]}
    </span>
  );
}
