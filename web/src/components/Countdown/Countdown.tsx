"use client";

import { useState } from "react";

import { useInterval } from "@/hooks/useInterval";
import { hms } from "@/lib/format";

import styles from "./Countdown.module.css";

type Props = {
  endsAt: number; // epoch ms, from the server
  serverOffsetMs?: number; // serverNow - clientNow, measured on connect
  label?: string;
  finishedLabel?: string;
};

/**
 * Remaining time, derived from server time (docs/frontend §7): the client never counts
 * down from page load. Only the changing seconds animate.
 */
export function Countdown({ endsAt, serverOffsetMs = 0, label = "remaining", finishedLabel = "finished" }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useInterval(() => setNow(Date.now()), 1000);
  const left = (endsAt - (now + serverOffsetMs)) / 1000;
  const text = hms(left);
  return (
    <div className={styles.wrap}>
      <div className={styles.label}>{left > 0 ? label : finishedLabel}</div>
      <div className={styles.clock} aria-live="off">
        {text.slice(0, -2)}
        <span key={text} className={styles.digit}>
          {text.slice(-2)}
        </span>
      </div>
    </div>
  );
}
