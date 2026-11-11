import { Spinner } from "@/components";

export default function Loading() {
  return (
    <div style={{ padding: "18px var(--gutter-wide)", color: "var(--fg-dim)" }}>
      <Spinner /> loading…
    </div>
  );
}
