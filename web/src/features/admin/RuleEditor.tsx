"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { AgreementMeter, Button, Field, Input, Notice, Select, SegmentedToggle, TextArea, VersionList } from "@/components";
import type { RuleVersion } from "@/components/VersionList/VersionList";

import styles from "./RuleEditor.module.css";

type JudgeType = "exact" | "gates" | "llm-rubric";

const THRESHOLD = 0.9;
const RUBRIC = `PASS when every check holds:
- the output is a JSON object with vendor, date, total and currency;
- date and currency equal the expected values exactly;
- total is within 0.01 of the expected total.
FAIL otherwise. Ignore key order and whitespace.`;

const HISTORY: RuleVersion[] = [
  { version: 1, status: "active", kappa: 0.94, author: "owner", sha: "5e1f0c2", createdAt: "2026-11-10", note: "json_schema + json_fields + numeric_tolerance gates" },
];

/**
 * Eval-rule editor (route /admin/rules/:id), on sample data until rule versioning ships
 * (M6). Saved versions are immutable; editing builds a new draft, any edit makes the
 * calibration stale, and "Activate" stays locked until a fresh run clears κ ≥ 0.90.
 * The server re-checks both on activation; this gate only explains the state.
 */
export function RuleEditor({ ruleName }: { ruleName: string }) {
  const [judge, setJudge] = useState<JudgeType>("gates");
  const [rubric, setRubric] = useState(RUBRIC);
  const [kappa, setKappa] = useState(0.86);
  const [stale, setStale] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [activated, setActivated] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  const touch = () => {
    setStale(true);
    setActivated(false);
  };
  const ok = kappa >= THRESHOLD && !stale && progress === null;

  const calibrate = () => {
    if (progress !== null) return;
    const from = kappa;
    const to = 0.93;
    let k = 0;
    setProgress(0);
    timer.current = setInterval(() => {
      k += 8;
      if (k >= 200) {
        clearInterval(timer.current!);
        setKappa(to);
        setProgress(null);
        setStale(false);
      } else {
        setProgress(k);
        setKappa(from + ((to - from) * k) / 200 + Math.sin(k) * 0.01);
      }
    }, 60);
  };

  const versions: RuleVersion[] = useMemo(
    () => [
      {
        version: 2,
        status: activated ? "active" : "draft",
        kappa: stale ? null : kappa,
        author: "you",
        createdAt: activated ? new Date().toISOString().slice(0, 16).replace("T", " ") : "unsaved",
        note: "accept totals within 0.01; ignore key order",
        sha: activated ? "c04be19" : undefined,
      },
      ...HISTORY.map((v) => (activated ? { ...v, status: "superseded" as const } : v)),
    ],
    [activated, kappa, stale],
  );
  const cm = kappa >= THRESHOLD ? { pp: 118, pf: 3, fp: 4, ff: 75 } : { pp: 111, pf: 8, fp: 8, ff: 73 };
  const gate = activated
    ? "v2 activated · v1 kept read-only"
    : progress !== null
      ? "calibration running"
      : stale
        ? "locked · calibration is stale"
        : kappa < THRESHOLD
          ? `locked · κ ${kappa.toFixed(2)} < ${THRESHOLD.toFixed(2)}`
          : "calibration passed";

  return (
    <div className={styles.view}>
      <div className={styles.grid}>
        <div className={styles.full}>
          <Notice tone="preview" tag="preview">
            sample data · rule versions and calibration arrive with the LLM judge (M6)
          </Notice>
        </div>
        <div className={styles.col}>
          <div>
            <div className={styles.dim}>admin / eval rules</div>
            <h1 className={styles.title}>
              er/{ruleName} <span className={styles.dim}>· editing</span> v2 <span className={styles.dim}>draft</span>
            </h1>
            <div className={styles.dim}>based on v1 · applies to every test of {ruleName}</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className={styles.dim}>judge type</span>
            <SegmentedToggle
              label="judge type"
              tone="soft"
              size="lg"
              value={judge}
              onChange={(v) => {
                setJudge(v);
                touch();
              }}
              options={[
                { value: "exact", label: "exact match" },
                { value: "gates", label: "deterministic gates" },
                { value: "llm-rubric", label: "llm rubric" },
              ]}
            />
          </div>
          <Field label="rubric">
            <TextArea rows={7} value={rubric} onChange={(e) => (setRubric(e.target.value), touch())} />
          </Field>
          <div className={styles.four}>
            <Field label="judge model">
              <Select onChange={touch} defaultValue="claude-haiku-4-5">
                <option>claude-haiku-4-5</option>
              </Select>
            </Field>
            <Field label="samples / item">
              <Input defaultValue="3" inputMode="numeric" onChange={touch} />
            </Field>
            <Field label="aggregation">
              <Select onChange={touch} defaultValue="majority">
                <option>majority</option>
                <option>unanimous</option>
                <option>mean ≥ thr</option>
              </Select>
            </Field>
            <Field label="judge temp">
              <Input defaultValue="0.0" inputMode="decimal" onChange={touch} />
            </Field>
          </div>
          <Field label="change note" hint="stored with the version, cannot be edited later">
            <Input defaultValue="accept totals within 0.01; ignore key order" />
          </Field>
          <div className={styles.actions}>
            <Button size="lg">Save draft</Button>
            <Button size="lg" variant={ok && !activated ? "success" : "ghost"} disabled={!ok || activated} onClick={() => setActivated(true)}>
              {activated ? "v2 active" : "Activate v2"}
            </Button>
            <span style={{ color: activated || ok ? "var(--verdict-pass)" : "var(--fg-dim)" }} aria-live="polite">
              {gate}
            </span>
          </div>
        </div>
        <div className={styles.colWide}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <AgreementMeter
              kappa={kappa}
              threshold={THRESHOLD}
              stale={stale}
              caption={progress !== null ? `scoring transcripts ${progress}/200 …` : "n = 200 labeled transcripts · 3 annotators"}
            />
            <div className={styles.matrix} role="table" aria-label="confusion matrix">
              <span />
              <span className={`${styles.dim} ${styles.num}`}>human pass</span>
              <span className={`${styles.dim} ${styles.num}`}>human fail</span>
              <span className={styles.dim}>rule pass</span>
              <span className={styles.num}>{cm.pp}</span>
              <span className={styles.num} style={{ color: "var(--verdict-fail)" }}>{cm.pf}</span>
              <span className={styles.dim}>rule fail</span>
              <span className={styles.num} style={{ color: "var(--verdict-fail)" }}>{cm.fp}</span>
              <span className={styles.num}>{cm.ff}</span>
            </div>
            <div>
              <Button size="lg" onClick={calibrate} disabled={progress !== null}>
                {progress !== null ? "Calibrating…" : "Run calibration"}
              </Button>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className={styles.versionsHead}>
              <span>version history</span>
              <span>published versions are immutable</span>
            </div>
            <VersionList versions={versions} />
          </div>
        </div>
      </div>
    </div>
  );
}
