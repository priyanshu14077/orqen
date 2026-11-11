"use client";

import { Button, Notice } from "@/components";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div style={{ padding: "18px var(--gutter-wide)", display: "flex", flexDirection: "column", gap: 12, maxWidth: 640 }}>
      <Notice tone="error" tag="error">
        Something failed while loading this screen. The judge is probably fine; try again.
      </Notice>
      <div>
        <Button variant="outline" size="md" onClick={reset}>
          Retry
        </Button>
      </div>
    </div>
  );
}
