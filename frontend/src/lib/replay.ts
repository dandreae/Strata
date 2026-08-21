/**
 * Staged-replay data helpers for fixture/demo mode.
 *
 * Everything here reads from an already-known, already-captured RunDetail
 * (real or synthetic, per lib/fixtures.ts) and either (a) picks values
 * directly off real per-candidate fields the backend already computed
 * (is_feasible, is_pareto_optimal, constraint_checks), or (b) does simple,
 * mechanical aggregation of those real fields for display (counts,
 * groupings) — it never re-runs or re-derives an optimization decision
 * (Pareto dominance, constraint pass/fail, selection) itself. That stays
 * backend-authoritative, per docs/architecture.md.
 *
 * One exception, clearly called out: ROUND1_ONLY_PARETO_IDS below. The
 * `is_pareto_optimal` flag on a candidate reflects the FINAL, combined-round
 * Pareto frontier (the real API contract) — it can't tell us what the
 * frontier looked like after Round 1 alone, which the replay needs for its
 * "reveal Round 1's frontier, then show it get dominated" moment. That
 * round-1-only frontier was computed once, offline, with the real
 * deterministic backend function (`app.optimization.pareto.pareto_frontier`)
 * against this fixture's real Round 1 data — not invented, not recomputed
 * here — and is simply looked up by candidate id.
 */

import type { Candidate, Decision, RunDetail } from "./api";

// Real ids from the real backend Pareto computation (see lib/fixtures.ts's
// enclosure-adaptive-benchmark comment for provenance). Only meaningful for
// that one fixture; harmless (empty match) for any other.
const ROUND1_ONLY_PARETO_IDS = new Set<string>([
  "0d0ae560-fd08-413a-8afd-a889c59bf3f3",
  "673d1057-82b6-4e51-bff7-94bcbc18464a",
]);

export function isRound1OnlyParetoOptimal(candidate: Candidate): boolean {
  return ROUND1_ONLY_PARETO_IDS.has(candidate.id);
}

export interface RoundLearningStats {
  total: number;
  violatedCount: number;
  feasibleCount: number;
  /** Distinct perimeter_count values used by feasible candidates, ascending. */
  feasiblePerimeters: number[];
  /** Highest infill_percent among feasible candidates. */
  maxFeasibleInfill: number | null;
}

/** Simple, mechanical aggregation over real per-candidate fields — no
 * dominance/constraint logic performed here, just counting and grouping
 * values the backend already flagged. */
export function computeRoundLearning(round1: Candidate[]): RoundLearningStats {
  const feasible = round1.filter((c) => c.is_feasible);
  const perimeters = Array.from(new Set(feasible.map((c) => c.perimeter_count))).sort((a, b) => a - b);
  const maxInfill = feasible.length > 0 ? Math.max(...feasible.map((c) => c.infill_percent)) : null;
  return {
    total: round1.length,
    violatedCount: round1.length - feasible.length,
    feasibleCount: feasible.length,
    feasiblePerimeters: perimeters,
    maxFeasibleInfill: maxInfill,
  };
}

export interface BeforeAfterStats {
  round1FeasiblePercent: number;
  round2FeasiblePercent: number;
  finalFrontierFromRound2Percent: number;
}

export function computeBeforeAfter(round1: Candidate[], round2: Candidate[], finalFrontier: Candidate[]): BeforeAfterStats {
  const pct = (n: number, total: number) => (total === 0 ? 0 : Math.round((n / total) * 100));
  const round1Feasible = round1.filter((c) => c.is_feasible).length;
  const round2Feasible = round2.filter((c) => c.is_feasible).length;
  const fromRound2 = finalFrontier.filter((c) => c.round === 2).length;
  return {
    round1FeasiblePercent: pct(round1Feasible, round1.length),
    round2FeasiblePercent: pct(round2Feasible, round2.length),
    finalFrontierFromRound2Percent: pct(fromRound2, finalFrontier.length),
  };
}

/** The real, backend-flagged final Pareto frontier, sorted fastest-first —
 * the natural order for a "Faster <-> Less material" slider. Only ever
 * reorders candidates the backend already marked is_pareto_optimal; invents
 * nothing. */
export function sortedFinalFrontier(run: RunDetail): Candidate[] {
  return run.candidates
    .filter((c) => c.is_pareto_optimal)
    .slice()
    .sort((a, b) => (a.print_time_seconds ?? 0) - (b.print_time_seconds ?? 0));
}

export function findDecision(run: RunDetail, actions: string[]): Decision | undefined {
  return run.decisions.find((d) => actions.includes(d.selected_action));
}
