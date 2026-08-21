import type { Candidate } from "../lib/api";
import { computeRoundLearning } from "../lib/replay";

/** The adaptation pivot — computed live from real per-candidate fields
 * (violated/feasible counts, which perimeter counts and infill levels the
 * feasible ones actually used). Describes what happened, never what Gemini
 * "thought" — no reasoning is invented. The closing line is only shown if
 * Round 2's real candidates actually concentrate in the same region Round
 * 1 found feasible — checked against real data, not assumed. */
export function RoundLearningPanel({ round1, round2 }: { round1: Candidate[]; round2?: Candidate[] }) {
  const stats = computeRoundLearning(round1);
  const perimText =
    stats.feasiblePerimeters.length === 1
      ? `${stats.feasiblePerimeters[0]} perimeters`
      : `${stats.feasiblePerimeters.join("–")} perimeters`;

  const targetedFollowUp =
    round2 &&
    round2.length > 0 &&
    stats.feasiblePerimeters.length > 0 &&
    round2.filter((c) => stats.feasiblePerimeters.includes(c.perimeter_count)).length / round2.length >= 0.75;

  return (
    <section className="result-card learning-panel">
      <span className="learning-eyebrow">Round 1 learning</span>
      <p className="learning-headline">
        {stats.violatedCount} of {stats.total} experiments violated constraints.
      </p>
      {stats.feasibleCount > 0 && (
        <p className="learning-detail">
          The {stats.feasibleCount} feasible configuration{stats.feasibleCount === 1 ? "" : "s"} concentrated
          around {perimText}
          {stats.maxFeasibleInfill !== null && <> and infill ≤{stats.maxFeasibleInfill}%</>}.
        </p>
      )}
      {targetedFollowUp && <p className="learning-action">Gemini's Round 2 proposals concentrated in that same region.</p>}
    </section>
  );
}
