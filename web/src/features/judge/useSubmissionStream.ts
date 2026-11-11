"use client";

import { useEffect, useReducer, useRef } from "react";

import type { JudgeEvent, Snapshot } from "@/lib/api/types";

import { fromSnapshot, isTerminal, judgeReducer } from "./reducer";

const EVENT_TYPES = ["meta", "status", "test", "completed"] as const;

/**
 * Snapshot first, then the event stream from its `seq` (docs/frontend §4.1).
 * Events are buffered and applied once per animation frame. A gap in `seq` refetches
 * the snapshot; later events then apply on top of it. EventSource reconnects by itself
 * after a network drop, sending Last-Event-ID so nothing is replayed twice.
 */
export function useSubmissionStream(initial: Snapshot) {
  const [state, dispatch] = useReducer(judgeReducer, initial, fromSnapshot);
  const seqRef = useRef(state.seq);
  useEffect(() => {
    seqRef.current = state.seq;
  }, [state.seq]);
  const done = isTerminal(state.status);

  useEffect(() => {
    if (done) return;
    let source: EventSource | null = null;
    let buffer: JudgeEvent[] = [];
    let frame = 0;

    const flush = () => {
      frame = 0;
      const batch = buffer;
      buffer = [];
      if (batch.length) dispatch({ type: "events", events: batch });
    };
    const open = () => {
      source = new EventSource(
        `/api/gw/v1/submissions/${initial.submission_id}/events?after=${seqRef.current}`,
      );
      for (const type of EVENT_TYPES) {
        source.addEventListener(type, (msg) => {
          const event = JSON.parse((msg as MessageEvent<string>).data) as JudgeEvent;
          buffer.push(event);
          if (!frame) frame = requestAnimationFrame(flush);
          if (event.type === "completed") source?.close();
        });
      }
    };
    open();
    return () => {
      source?.close();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [initial.submission_id, done]);

  // Gap recovery: refetch the snapshot; the effect above reconnects from its seq.
  useEffect(() => {
    if (!state.resync) return;
    let cancelled = false;
    fetch(`/api/gw/v1/submissions/${initial.submission_id}`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Snapshot>) : null))
      .then((snap) => {
        if (snap && !cancelled) dispatch({ type: "snapshot", snapshot: snap });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [state.resync, initial.submission_id]);

  return state;
}
