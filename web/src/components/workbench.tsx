"use client";

import { useState } from "react";

import { ALL_ROWS } from "./fixtures";
import {
  AgreementMeter,
  Button,
  Countdown,
  Handle,
  LimitsHeader,
  LogHeader,
  LogRow,
  MetaRow,
  Notice,
  PipelineBreadcrumb,
  RetryTag,
  SegmentedToggle,
  StandingsHeader,
  StandingsRow,
  StatusBar,
  VerdictLabel,
  VersionList,
} from "./index";
import { STAGES } from "./PipelineBreadcrumb/PipelineBreadcrumb";
import { VERDICTS } from "@/lib/format";

type Story = () => React.ReactNode;

export const Verdicts: Story = () => (
  <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
    {VERDICTS.map((v) => (
      <VerdictLabel key={v} verdict={v} />
    ))}
    <VerdictLabel verdict={null} />
    <RetryTag attempt={1} max={3} />
  </div>
);

export const Pipeline: Story = () => (
  <>
    {STAGES.map((s) => (
      <PipelineBreadcrumb key={s} status={s} done={3} total={8} />
    ))}
    <PipelineBreadcrumb status="FAILED" />
  </>
);

export const Log: Story = () => {
  const [open, setOpen] = useState<Record<number, boolean>>({ 2: true });
  return (
    <div>
      <LogHeader />
      <MetaRow ts="2026-11-11T14:02:07.600Z" text="expand  8 tests (3 sample, 5 hidden)" />
      {ALL_ROWS.map((e) => (
        <LogRow key={e.seq} event={e} expanded={Boolean(open[e.seq])} onToggle={() => setOpen((o) => ({ ...o, [e.seq]: !o[e.seq] }))} />
      ))}
      <LogRow event={{ ...ALL_ROWS[0], seq: 99, test: 9 }} expanded onToggle={() => undefined} live />
    </div>
  );
};

export const StatusBars: Story = () => (
  <>
    {(["idle", "running", "done", "failed"] as const).map((tone) => (
      <StatusBar
        key={tone}
        mode={tone.toUpperCase()}
        tone={tone}
        left={[{ content: "sub/48213abc", strong: true }, { content: "invoice-extractor" }]}
        right={[{ content: "score 87.5/100" }, { content: "seq 000042", strong: true }]}
      />
    ))}
  </>
);

export const Limits: Story = () => (
  <LimitsHeader timeMs={60000} memoryMb={256} tokenBudget={8000} maxSteps={6} models={["claude-haiku-4-5"]} />
);

export const Controls: Story = () => {
  const [v, setV] = useState<"prompt" | "code">("prompt");
  return (
    <>
      <SegmentedToggle label="editor" value={v} onChange={setV} options={[{ value: "prompt", label: "prompt" }, { value: "code", label: "code" }]} />
      <div style={{ display: "flex", gap: 8 }}>
        <Button>[e] expand all</Button>
        <Button variant="outline" size="md">Run samples</Button>
        <Button variant="primary" size="md">Submit</Button>
        <Button variant="success" size="lg">Activate v2</Button>
        <Button disabled>disabled</Button>
      </div>
      {(["error", "warn", "info", "preview"] as const).map((t) => (
        <Notice key={t} tone={t} tag={t}>
          an inline {t} message
        </Notice>
      ))}
    </>
  );
};

export const Handles: Story = () => (
  <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
    <Handle handle="alice" />
    <Handle handle="alice" you />
    {[1100, 1300, 1500, 1800, 2000, 2300, 2600, 3100].map((r) => (
      <Handle key={r} handle={`tier_${r}`} rating={r} showRating />
    ))}
  </div>
);

// A fixed end time; the countdown shows "finished" once it has passed.
const CONTEST_END = Date.parse("2027-01-01T00:00:00Z");

export const Scoreboard: Story = () => (
  <div>
    <Countdown endsAt={CONTEST_END} />
    <StandingsHeader problems={[{ label: "A", points: 500 }, { label: "B", points: 1000 }, { label: "C", points: 1500 }]} />
    <StandingsRow row={{ rank: 1, handle: "kv_cache", score: 2864, tokensK: 43.1, tie: false, you: false, cells: [{ state: "solved", points: 492, tokensK: 6.2 }, { state: "solved", points: 968, tokensK: 14.1 }, { state: "solved", points: 1404, tokensK: 22.8 }] }} />
    <StandingsRow row={{ rank: 2, handle: "alice", score: 1400, tokensK: 21.3, tie: true, you: true, cells: [{ state: "solved", points: 488, tokensK: 5.5 }, { state: "solved", points: 912, tokensK: 15.8 }, { state: "judging" }] }} />
    <StandingsRow row={{ rank: 3, handle: "zfunc", score: 1400, tokensK: 26.4, tie: true, you: false, cells: [{ state: "solved", points: 484, tokensK: 6.1 }, { state: "failed", attempts: 2 }, { state: "none" }] }} />
  </div>
);

export const Calibration: Story = () => (
  <div style={{ maxWidth: 420, display: "flex", flexDirection: "column", gap: 28 }}>
    <AgreementMeter kappa={0.93} threshold={0.9} caption="n = 200 labeled transcripts" />
    <AgreementMeter kappa={0.84} threshold={0.9} />
    <AgreementMeter kappa={0.84} threshold={0.9} stale />
    <VersionList
      versions={[
        { version: 2, status: "draft", kappa: null, author: "you", createdAt: "unsaved", note: "accept totals within 0.01" },
        { version: 1, status: "active", kappa: 0.94, author: "owner", sha: "5e1f0c2", createdAt: "2026-11-10", note: "gates" },
        { version: 0, status: "rejected", kappa: 0.79, author: "owner", sha: "e8d0442", createdAt: "2026-11-01", note: "failed calibration" },
      ]}
    />
  </div>
);

/** Every fixture, in the order the workbench shows them. */
export const STORIES: [string, Story][] = [
  ["verdicts", Verdicts],
  ["pipeline", Pipeline],
  ["log", Log],
  ["status bar", StatusBars],
  ["limits", Limits],
  ["controls", Controls],
  ["handles", Handles],
  ["scoreboard", Scoreboard],
  ["calibration", Calibration],
];
