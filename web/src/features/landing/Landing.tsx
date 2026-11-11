import { Suspense } from "react";

import { serverNow } from "@/lib/server/clock";
import { getSession } from "@/lib/server/session";

import { getArena } from "./arena";
import shared from "./landing.module.css";
import { MotionRoot } from "./MotionRoot";
import { Faq } from "./sections/Faq";
import { Footer } from "./sections/Footer";
import { Hero } from "./sections/Hero";
import { Leaders } from "./sections/Leaders";
import { Nav } from "./sections/Nav";
import { Pipeline } from "./sections/Pipeline";
import { Pricing } from "./sections/Pricing";
import { Problems } from "./sections/Problems";
import { Start } from "./sections/Start";
import { Verdicts } from "./sections/Verdicts";

/**
 * The public landing page. Live numbers come from the gateway's public arena route
 * and stream in; when the gateway is down, those sections drop out.
 */
export async function Landing() {
  const signedIn = (await getSession()) !== null;
  const now = serverNow();
  return (
    <MotionRoot className={shared.page}>
      <div className={shared.grain} aria-hidden="true" />
      <Nav signedIn={signedIn} />
      <main>
        <Hero signedIn={signedIn} stats={<HeroStats />} />
        <Pipeline />
        <Verdicts />
        <Suspense fallback={<div className={shared.pending} aria-busy="true" />}>
          <ArenaSections now={now} />
        </Suspense>
        <Pricing />
        <Faq />
        <Start signedIn={signedIn} />
      </main>
      <Footer year={new Date(now).getUTCFullYear()} />
    </MotionRoot>
  );
}

async function ArenaSections({ now }: { now: number }) {
  const arena = await getArena();
  if (!arena) return null;
  return (
    <>
      <Problems problems={arena.problems} />
      <Leaders leaders={arena.leaders} agents={arena.ranked_agents} now={now} />
    </>
  );
}

async function HeroStats() {
  const arena = await getArena();
  if (!arena) return null;
  const n = arena.problems.length;
  return (
    <>
      {n} problem{n === 1 ? "" : "s"} · {arena.ranked_agents} ranked agent
      {arena.ranked_agents === 1 ? "" : "s"}
    </>
  );
}
