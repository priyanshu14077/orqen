"use client";

import { type RefObject, useCallback, useEffect, useRef, useState } from "react";

const THRESHOLD_PX = 40;

/**
 * Auto-scroll for a growing log (docs/frontend §4.5). The view follows new content
 * while the reader is within 40px of the bottom; scrolling up or expanding a row
 * releases it, and `stick()` re-engages it.
 */
export function useStickToBottom(ref: RefObject<HTMLElement | null>, contentKey: unknown) {
  const stuck = useRef(true);
  const [following, setFollowing] = useState(true);
  const [unseen, setUnseen] = useState(0);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD_PX;
    stuck.current = atBottom;
    setFollowing(atBottom);
    if (atBottom) setUnseen(0);
  }, [ref]);

  const release = useCallback(() => {
    stuck.current = false;
    setFollowing(false);
  }, []);

  const stick = useCallback(() => {
    stuck.current = true;
    setFollowing(true);
    setUnseen(0);
    const el = ref.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [ref]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (stuck.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } else {
      setUnseen((n) => n + 1);
    }
  }, [ref, contentKey]);

  return { following, unseen, onScroll, release, stick };
}
