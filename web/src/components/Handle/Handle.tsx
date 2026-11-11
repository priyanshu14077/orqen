import styles from "./Handle.module.css";

/**
 * Rating tiers from the reference build. Ratings aren't in the product yet, so a
 * handle without one renders in the plain foreground colour; when ratings ship, the
 * thresholds should come from the server's config, not this table.
 */
const TIERS: [number, string][] = [
  [1200, "#8b949e"],
  [1400, "#4caf50"],
  [1600, "#39c5bb"],
  [1900, "#5b8cff"],
  [2100, "#b26bff"],
  [2400, "#ff9f1a"],
  [3000, "#ff4d4d"],
];

export function tierColors(rating: number): [string, string] {
  if (rating >= 3000) return ["var(--fg-bright)", "#ff4d4d"];
  const c = TIERS.find(([max]) => rating < max)?.[1] ?? "#ff4d4d";
  return [c, c];
}

type Props = { handle: string; rating?: number | null; you?: boolean; showRating?: boolean };

export function Handle({ handle, rating, you = false, showRating = false }: Props) {
  const [first, rest] = rating == null ? ["var(--fg)", "var(--fg)"] : tierColors(rating);
  return (
    <span className={styles.handle}>
      <span style={{ color: first }}>{handle[0]}</span>
      <span style={{ color: rest }}>{handle.slice(1)}</span>
      {showRating && rating != null && <span className={styles.rating}>{rating}</span>}
      {you && <span className={styles.you}>(you)</span>}
    </span>
  );
}
