import type { Verdict } from "@/lib/api/types";

export const VERDICTS: Verdict[] = ["PASS", "FAIL", "TLE", "MLE", "ERROR", "BUDGET", "SYSTEM_ERROR"];

/** The token each verdict is drawn with (docs/frontend Table 4). */
export const VERDICT_TOKEN: Record<Verdict, string> = {
  PASS: "var(--verdict-pass)",
  FAIL: "var(--verdict-fail)",
  TLE: "var(--verdict-limit)",
  MLE: "var(--verdict-limit)",
  ERROR: "var(--verdict-error)",
  BUDGET: "var(--verdict-budget)",
  SYSTEM_ERROR: "var(--verdict-system)",
};

export const int = (n: number) => n.toLocaleString("en-US");

export function compactTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export function seconds(ms: number | null | undefined): string {
  return ms == null ? "…" : `${(ms / 1000).toFixed(1)}s`;
}

export function clockTime(iso: string): string {
  const d = new Date(iso);
  const pad = (v: number, w = 2) => String(v).padStart(w, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

export function hms(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const pad = (v: number) => String(v).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

export function relative(iso: string, now = Date.now()): string {
  const diff = Math.max(0, now - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export const score100 = (s: number | null | undefined) => (s == null ? "—" : s.toFixed(1));

/** Deterministic pseudo-random widths for redacted traces, seeded by test number. */
export function redactedWidths(test: number, steps: number, max = 5): number[] {
  return Array.from({ length: Math.min(steps, max) }, (_, j) => 18 + ((test * 37 + j * 53) % 70));
}
