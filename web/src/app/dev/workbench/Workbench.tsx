"use client";

import { STORIES } from "@/components/workbench";

export function Workbench() {
  return (
    <main style={{ padding: "16px var(--gutter-wide) 60px", display: "flex", flexDirection: "column", gap: 28 }}>
      <h1 style={{ margin: 0, color: "var(--fg-bright)", fontSize: "var(--text-xl)", fontWeight: 300 }}>
        component workbench
      </h1>
      <nav style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        {STORIES.map(([name]) => (
          <a key={name} href={`#${name.replace(" ", "-")}`}>
            {name}
          </a>
        ))}
      </nav>
      {STORIES.map(([name, Story]) => (
        <section key={name} id={name.replace(" ", "-")} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <h2 style={{ margin: 0, color: "var(--fg-dim)", fontSize: "inherit", fontWeight: 400 }}>## {name}</h2>
          <div style={{ border: "1px solid var(--line)", padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
            <Story />
          </div>
        </section>
      ))}
    </main>
  );
}
