"use client";

import { useCountUp } from "@/hooks/useCountUp";

/** A number that eases to its new value: the final score, totals. */
export function CountUp({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const shown = useCountUp(value);
  return <>{shown.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</>;
}
