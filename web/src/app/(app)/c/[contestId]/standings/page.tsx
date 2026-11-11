import type { Metadata } from "next";

import { ContestBoard } from "@/features/contest/ContestBoard";
import { serverNow as now } from "@/lib/server/clock";
import { getMe } from "@/lib/server/viewer";

export const metadata: Metadata = { title: "standings" };

// The preview contest ends 2h14m37s after the hour it is viewed in, so the clock is
// stable across reloads within that hour. The server sends its own time for the offset.
export default async function StandingsPage() {
  const me = await getMe();
  const serverNow = now();
  const hour = Math.floor(serverNow / 3_600_000) * 3_600_000;
  return <ContestBoard handle={me.handle} serverNow={serverNow} endsAt={hour + (2 * 3600 + 14 * 60 + 37) * 1000} />;
}
