"use client";

import { useEffect, useRef, useState } from "react";

import { createReplay, type Line, type Progress, TESTS } from "../replay";
import styles from "./Hero.module.css";

const ROWS = 34;
const TICK_MS = 420;

function seed() {
  const replay = createReplay();
  const lines: Line[] = Array.from({ length: ROWS }, () => replay.next());
  return { replay, lines, progress: replay.progress() };
}

/**
 * The hero's background: a judge log replaying scripted submissions, one line per
 * test. Pauses while off screen or in a background tab; static under reduced motion.
 */
export function HeroReplay() {
  const [{ replay, lines: first, progress: firstProgress }] = useState(seed);
  const [lines, setLines] = useState(first);
  const [progress, setProgress] = useState<Progress>(firstProgress);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = true;
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    });
    if (box.current) io.observe(box.current);
    const id = window.setInterval(() => {
      if (!visible || document.hidden) return;
      const line = replay.next();
      setLines((ls) => [...ls.slice(1), line]);
      setProgress(replay.progress());
    }, TICK_MS);
    return () => {
      window.clearInterval(id);
      io.disconnect();
    };
  }, [replay]);

  return (
    <>
      <div ref={box} className={styles.log} aria-hidden="true">
        {lines.map((l) =>
          l.kind === "summary" ? (
            <div key={l.key} className={`${styles.row} ${styles.summary}`}>
              ── sub/{l.submission} COMPLETED · {l.score} / {TESTS * 50} · {l.passed}/{TESTS} pass ·{" "}
              {l.tokens.toLocaleString("en-US")} tok ──
            </div>
          ) : (
            <div key={l.key} className={styles.row}>
              <span>{l.ts}</span>
              <span>#{String(l.test).padStart(2, "0")}</span>
              <span>{l.scope}</span>
              <span className={styles.verdict} data-v={l.verdict}>
                {l.verdict}
              </span>
              <span className={styles.num}>{l.retry ?? l.tokens.toLocaleString("en-US")}</span>
              <span className={styles.num}>{l.steps || "—"}</span>
              <span className={styles.num}>{l.latency}</span>
            </div>
          ),
        )}
      </div>
      <div className={styles.chip} role="status" aria-label="judge replay">
        <span className={styles.dot} aria-hidden="true" />
        <span>replay</span>
        <span className={styles.chipDim}>sub/{progress.submission}</span>
        <span>
          test {progress.test}/{TESTS}
        </span>
        <span className={styles.chipBright}>{progress.score} / {TESTS * 50}</span>
        <span className={styles.chipDim}>{progress.tokens.toLocaleString("en-US")} tok</span>
      </div>
    </>
  );
}
