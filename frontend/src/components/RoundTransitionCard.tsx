import type { Decision } from "../lib/api";

/**
 * The pivot moment: the agent used Round 1's real measurements to decide
 * whether a second, targeted round is worth running. Shared between the
 * final results view and the replay experience so the demo's most
 * important beat looks identical in both.
 *
 * The headline and the "N new configurations" count are computed from real
 * data already available to the caller (never invented); the quoted line
 * is Gemini's own real `reasoning_summary` text, verbatim, when present —
 * the one piece of genuine natural-language reasoning worth surfacing
 * directly rather than only in the collapsible trace.
 */
export function RoundTransitionCard({ decision, round2Count }: { decision: Decision; round2Count: number }) {
  const reasoning = decision.evidence[0];

  if (decision.selected_action === "round_two_unavailable") {
    return (
      <section className="result-card round-transition-card round-transition-unavailable">
        <span className="round-transition-eyebrow">Adaptive decision</span>
        <h2 className="round-transition-headline">Round 2 planning failed — Round 1 results stand</h2>
        <p className="round-transition-detail">Nothing measured in Round 1 is discarded.</p>
      </section>
    );
  }

  const continuing = decision.selected_action === "continue_optimization";
  return (
    <section
      className={`result-card round-transition-card ${continuing ? "round-transition-continue" : "round-transition-stop"}`}
    >
      <span className="round-transition-eyebrow">Adaptive decision</span>
      <h2 className="round-transition-headline">
        Gemini evaluated Round 1 → {continuing ? "targeted search" : "stopped searching"}
      </h2>
      <p className="round-transition-detail">
        {continuing
          ? `${round2Count} new configuration${round2Count === 1 ? "" : "s"} selected based on measured results.`
          : "Round 1's measured results already satisfy the search — no further experiments proposed."}
      </p>
      {reasoning && <p className="round-transition-quote">“{reasoning}”</p>}
    </section>
  );
}
