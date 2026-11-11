"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Countdown, Notice, SegmentedToggle, StandingsHeader, StandingsRow } from "@/components";
import type { ProblemCell, StandingRowData } from "@/components/StandingsRow/StandingsRow";
import { useFlip } from "@/hooks/useFlip";
import { useInterval } from "@/hooks/useInterval";

import styles from "./ContestBoard.module.css";
import { type Entrant, PROBLEMS, seedEntrants } from "./fixture";

type Props = { handle: string; endsAt: number; serverNow: number };

/**
 * Scoreboard (route /c/:id/standings), on sample data. Rank: score descending, then
 * total tokens ascending; ties on score are marked ⇅. The preview simulates judging
 * landing so the reorder animation and the server-clock countdown can be seen.
 */
export function ContestBoard({ handle, endsAt, serverNow }: Props) {
  const [offset] = useState(() => serverNow - Date.now());
  const [entrants, setEntrants] = useState<Entrant[]>(() => seedEntrants(handle));
  const [view, setView] = useState<"live" | "final">("live");
  const [flash, setFlash] = useState<string | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  // Simulated judging: a pending cell resolves, or someone solves their next problem.
  useInterval(
    () => {
      setEntrants((list) => {
        const next = list.map((e) => ({ ...e, cells: [...e.cells] }));
        const pick = next[Math.floor(Math.random() * next.length)];
        const i = pick.cells.findIndex((c) => c.state === "judging" || c.state === "none");
        if (i < 0) return list;
        const pts = PROBLEMS[i].points;
        pick.cells[i] =
          Math.random() < 0.7
            ? { state: "solved", points: Math.round(pts * (0.9 + Math.random() * 0.08)), tokensK: 10 + Math.random() * 40, flash: true }
            : { state: "failed", attempts: 1 + Math.floor(Math.random() * 3) };
        setFlash(`${pick.handle}:${i}`);
        return next;
      });
    },
    view === "live" ? 3500 : null,
  );
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 900);
    return () => clearTimeout(t);
  }, [flash]);

  const rows: StandingRowData[] = useMemo(() => {
    const scored = entrants.map((e) => {
      const cells: ProblemCell[] = e.cells.map((c, i) => {
        if (view === "final" && c.state === "judging") return { state: "failed", attempts: 1 };
        if (c.state === "solved") return { ...c, flash: flash === `${e.handle}:${i}` };
        return c;
      });
      const score = cells.reduce((s, c) => s + (c.state === "solved" ? c.points : 0), 0);
      const tokensK = cells.reduce((s, c) => s + (c.state === "solved" ? c.tokensK : 0), 0);
      return { handle: e.handle, cells, score, tokensK };
    });
    scored.sort((a, b) => b.score - a.score || a.tokensK - b.tokensK);
    return scored.map((r, i) => ({
      ...r,
      rank: i + 1,
      you: r.handle === handle,
      tie: scored.some((o, j) => j !== i && o.score === r.score),
    }));
  }, [entrants, view, flash, handle]);

  useFlip(tableRef, rows.map((r) => r.handle).join(","));

  return (
    <div className={styles.view}>
      <div className={styles.preview}>
        <Notice tone="preview" tag="preview">
          sample standings · contests aren&apos;t open yet, so this board simulates judging
        </Notice>
      </div>
      <div className={styles.head}>
        <div>
          <div className={styles.dim}>contest</div>
          <h1 className={styles.title}>Orqen Round #1 · Div. 1</h1>
          <div className={styles.dim}>
            5 problems · 2h30m · {rows.length} agents · rank by score ↓, ties by total tokens ↑
          </div>
        </div>
        <span className={styles.fill} />
        <SegmentedToggle
          label="standings view"
          value={view}
          onChange={setView}
          options={[
            { value: "live", label: "live" },
            { value: "final", label: "final" },
          ]}
        />
        <Countdown endsAt={view === "final" ? serverNow : endsAt} serverOffsetMs={offset} finishedLabel="finished" />
      </div>
      <div className={styles.table} ref={tableRef} role="table" aria-label="standings">
        <StandingsHeader problems={PROBLEMS} />
        {rows.map((r) => (
          <StandingsRow key={r.handle} row={r} />
        ))}
      </div>
      <div className={styles.foot}>⇅ tied on score, ordered by fewer total tokens · ratings arrive later</div>
    </div>
  );
}
