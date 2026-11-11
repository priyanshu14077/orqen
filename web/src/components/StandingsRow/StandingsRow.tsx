import { Handle } from "../Handle/Handle";
import styles from "./StandingsRow.module.css";

export type ProblemCell =
  | { state: "solved"; points: number; tokensK: number; flash?: boolean }
  | { state: "failed"; attempts: number }
  | { state: "judging" }
  | { state: "none" };

export type StandingRowData = {
  rank: number;
  handle: string;
  score: number;
  tokensK: number;
  tie: boolean;
  you: boolean;
  cells: ProblemCell[];
};

export function StandingsHeader({ problems }: { problems: { label: string; points: number }[] }) {
  return (
    <div
      className={styles.head}
      style={{ ["--problems" as string]: problems.length }}
      role="row"
    >
      <span role="columnheader">#</span>
      <span role="columnheader">AGENT</span>
      <span role="columnheader" style={{ textAlign: "right" }}>SCORE</span>
      <span role="columnheader" style={{ textAlign: "right" }}>TOKENS</span>
      {problems.map((p) => (
        <span key={p.label} role="columnheader" className={styles.center}>
          {p.label} <span className={styles.points}>{p.points}</span>
        </span>
      ))}
    </div>
  );
}

function Cell({ cell }: { cell: ProblemCell }) {
  switch (cell.state) {
    case "solved":
      return (
        <span className={styles.cell} role="cell" data-flash={cell.flash}>
          <span className={styles.a} style={{ color: "var(--verdict-pass)" }}>+{cell.points}</span>
          <span className={styles.b}>{cell.tokensK.toFixed(1)}k</span>
        </span>
      );
    case "failed":
      return (
        <span className={styles.cell} role="cell">
          <span className={styles.a} style={{ color: "var(--verdict-fail)" }}>−{cell.attempts}</span>
          <span className={styles.b}>&nbsp;</span>
        </span>
      );
    case "judging":
      return (
        <span className={styles.cell} role="cell">
          <span className={styles.a} style={{ color: "var(--verdict-limit)" }}>?</span>
          <span className={styles.b}>judging</span>
        </span>
      );
    default:
      return (
        <span className={styles.cell} role="cell">
          <span className={styles.a} style={{ color: "var(--sep)" }}>·</span>
          <span className={styles.b}>&nbsp;</span>
        </span>
      );
  }
}

/** One scoreboard row. The rank shown is the server's; the client only animates moves. */
export function StandingsRow({ row }: { row: StandingRowData }) {
  return (
    <div
      className={styles.row}
      data-you={row.you}
      data-flip-key={row.handle}
      style={{ ["--problems" as string]: row.cells.length }}
      role="row"
    >
      <span className={styles.rank} role="cell">{row.rank}</span>
      <span role="cell">
        <Handle handle={row.handle} you={row.you} />
      </span>
      <span className={styles.score} role="cell">{row.score}</span>
      <span className={styles.tokens} data-tie={row.tie} role="cell">
        {row.tokensK.toFixed(1)}k{row.tie ? " ⇅" : ""}
      </span>
      {row.cells.map((c, i) => (
        <Cell key={i} cell={c} />
      ))}
    </div>
  );
}
