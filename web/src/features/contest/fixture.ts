import type { ProblemCell } from "@/components/StandingsRow/StandingsRow";

/**
 * Sample standings for the scoreboard preview, from the reference build. Contests have
 * tables but no API yet; this goes away when the standings endpoint lands.
 */
export const PROBLEMS = [
  { label: "A", points: 500 },
  { label: "B", points: 1000 },
  { label: "C", points: 1500 },
  { label: "D", points: 2000 },
  { label: "E", points: 2500 },
];

type Seed = [handle: string, cells: string[]];

const SEED: Seed[] = [
  ["kv_cache", ["S492 6.2", "S968 14.1", "S1404 22.8", "S1720 41.0", "F3"]],
  ["nullptr_ex", ["S488 5.9", "S952 12.7", "S1380 25.4", "S1764 38.2", "-"]],
  ["greedy_decode", ["S490 7.1", "S944 16.0", "S1356 29.9", "F2", "S2010 58.3"]],
  ["aho_corasick", ["S486 6.8", "S960 13.3", "S1392 24.0", "P", "-"]],
  ["mxp", ["S494 5.1", "S936 18.4", "S1368 27.7", "-", "-"]],
  ["beam_k8", ["S480 8.0", "S928 19.9", "S1390 21.2", "-", "-"]],
  ["segtree_sam", ["S476 6.9", "S920 17.2", "F4", "-", "-"]],
  ["you", ["S488 5.5", "S912 15.8", "P", "-", "-"]],
  ["zfunc", ["S484 6.1", "S900 20.3", "-", "-", "-"]],
  ["lazy_prop", ["S470 9.4", "F2", "S1320 33.0", "-", "-"]],
  ["qwerty_rl", ["S466 10.2", "S904 22.6", "-", "-", "-"]],
  ["dsu_on_tree", ["S482 7.7", "F3", "-", "-", "-"]],
  ["k_lowest", ["S470 8.8", "-", "-", "-", "-"]],
  ["antimatroid", ["F2", "-", "-", "-", "-"]],
];

function parse(c: string): ProblemCell {
  if (c[0] === "S") {
    const [p, t] = c.slice(1).split(" ");
    return { state: "solved", points: Number(p), tokensK: Number(t) };
  }
  if (c[0] === "F") return { state: "failed", attempts: Number(c.slice(1)) };
  if (c === "P") return { state: "judging" };
  return { state: "none" };
}

export type Entrant = { handle: string; cells: ProblemCell[] };

export function seedEntrants(youHandle: string): Entrant[] {
  return SEED.map(([h, cells]) => ({ handle: h === "you" ? youHandle : h, cells: cells.map(parse) }));
}
