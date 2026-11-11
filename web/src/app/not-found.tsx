import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ minHeight: "60vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ color: "var(--fg-bright)", fontSize: "var(--text-display)", fontWeight: 300 }}>404</div>
        <div style={{ color: "var(--fg-dim)" }}>no such page, or it isn&apos;t open to you</div>
        <Link href="/">back to problems</Link>
      </div>
    </main>
  );
}
