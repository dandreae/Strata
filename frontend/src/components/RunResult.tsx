import type { Candidate, Decision, OptimizationSummary, RunDetail } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";
import { sortedFinalFrontier } from "../lib/replay";
import { ParetoChart } from "./ParetoChart";
import { RoundSection } from "./RoundSection";
import { RecommendationCard } from "./RecommendationCard";
import { RoundTransitionCard } from "./RoundTransitionCard";
import { DecisionLedger } from "./DecisionLedger";
import { TradeoffSlider } from "./TradeoffSlider";

const ROUND_TWO_ACTIONS = new Set(["continue_optimization", "stop_optimization", "round_two_unavailable"]);
const FINAL_ACTIONS = new Set(["select_candidate", "no_feasible_candidate", "escalate_tradeoff", "abort_run"]);

function SummaryCard({ summary, roundsRun }: { summary: OptimizationSummary; roundsRun: number }) {
  return (
    <section className="result-card">
      <h2>Optimization summary</h2>
      <p className="summary-line">
        <strong>{summary.candidates_tested}</strong> candidates tested across <strong>{roundsRun}</strong>{" "}
        round{roundsRun === 1 ? "" : "s"} &nbsp;·&nbsp; <strong>{summary.succeeded}</strong> sliced successfully
        &nbsp;·&nbsp; <strong>{summary.feasible}</strong> feasible &nbsp;·&nbsp; <strong>{summary.pareto_optimal}</strong>{" "}
        Pareto-optimal
      </p>
    </section>
  );
}

/** What the planner (deterministic or Gemini+ADK) proposed for Round 1,
 * before any slicing happened. Headline is a concise, user-facing count —
 * the raw backend wrapper string ("Planner 'gemini:gemini-3.5-flash'
 * proposed...") stays available verbatim in the Decision Ledger below. */
function PlanCard({ decision, candidateCount }: { decision: Decision; candidateCount: number }) {
  const strategy = decision.evidence[0];
  return (
    <section className="result-card">
      <h2>Round 1 — experiment plan</h2>
      <p className="decision-observation">
        Gemini proposed {candidateCount} experiment{candidateCount === 1 ? "" : "s"}.
      </p>
      {strategy && (
        <>
          <p className="decision-evidence-heading">Strategy</p>
          <p className="decision-outcome">“{strategy}”</p>
        </>
      )}
    </section>
  );
}

/** No candidate was selected — explains why (infeasible / tradeoff / technical failure). */
function NoWinnerCard({ run, decision }: { run: RunDetail; decision: Decision | undefined }) {
  if (run.status === "failed") {
    const firstFailure = run.candidates.find((c) => c.failure_reason)?.failure_reason;
    return (
      <section className="result-card result-card-error">
        <h2>Optimization did not complete</h2>
        <p>{firstFailure ?? decision?.outcome ?? "Slicing failed for an unknown reason."}</p>
      </section>
    );
  }

  if (run.status === "infeasible") {
    return (
      <section className="result-card result-card-error">
        <h2>No feasible configuration found</h2>
        <p>
          {run.optimization_summary.candidates_tested} configurations were tested and none satisfied your hard
          constraints. Try relaxing the max print time or max material limits.
        </p>
      </section>
    );
  }

  if (run.status === "needs_human_input") {
    const frontier = sortedFinalFrontier(run);
    return (
      <section className="result-card result-card-pending">
        <span className="selected-badge selected-badge-pending">Search complete — your call</span>
        <h2>Strata handled the engineering search. One preference remains yours.</h2>
        <p className="pending-subhead">
          Every remaining option below is Pareto-optimal — none is objectively better on both axes, so Strata
          asks rather than guesses.
        </p>
        <p className="decision-observation">
          {decision?.outcome ??
            "Several feasible candidates are mutually non-dominated and no optimization priority resolves the tradeoff."}
        </p>
        {frontier.length > 0 ? (
          <TradeoffSlider frontier={frontier} />
        ) : (
          <p className="decision-observation">No Pareto-optimal candidates were available to compare.</p>
        )}
      </section>
    );
  }

  return null;
}

const STATUS_LABELS: Record<string, string> = {
  succeeded: "✓",
  failed: "✕ slicing failed",
  pending: "…",
  slicing: "…",
};

function ComparisonTable({ run }: { run: RunDetail }) {
  return (
    <section className="result-card">
      <h2>All candidates tested</h2>
      <div className="comparison-scroll">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>Round</th>
              <th>Layer / Infill / Walls</th>
              <th>Time</th>
              <th>Material</th>
              <th>Feasible</th>
              <th>Pareto</th>
            </tr>
          </thead>
          <tbody>
            {run.candidates.map((candidate, i) => (
              <tr key={candidate.id} className={candidate.is_selected ? "comparison-row-selected" : ""}>
                <td>
                  #{i + 1}
                  {candidate.is_selected && <span className="row-selected-tag">SELECTED</span>}
                </td>
                <td>{candidate.round}</td>
                <td>
                  {candidate.layer_height.toFixed(2)}mm / {candidate.infill_percent}% / {candidate.perimeter_count}
                </td>
                <td>
                  {candidate.status === "succeeded" && candidate.print_time_seconds !== null
                    ? formatDuration(candidate.print_time_seconds)
                    : STATUS_LABELS[candidate.status]}
                </td>
                <td>
                  {candidate.status === "succeeded" && candidate.filament_grams !== null
                    ? formatGrams(candidate.filament_grams)
                    : "—"}
                </td>
                <td className={candidate.is_feasible ? "cell-pass" : "cell-fail"}>
                  {candidate.status === "succeeded" ? (candidate.is_feasible ? "✓" : "✕") : "—"}
                </td>
                <td>{candidate.is_pareto_optimal ? "✓" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RunResult({ run }: { run: RunDetail }) {
  const planDecision = run.decisions.find((d) => d.selected_action === "plan_initial_candidates");
  const roundTwoDecision = run.decisions.find((d) => ROUND_TWO_ACTIONS.has(d.selected_action));
  const finalDecision = run.decisions.find((d) => FINAL_ACTIONS.has(d.selected_action));
  const winner = run.candidates.find((c) => c.is_selected);

  if (run.candidates.length === 0) {
    // Planning itself failed (e.g. Gemini call errored) — no candidates
    // ever existed to slice. See _finish_run_planning_failed in the backend.
    return (
      <div className="results">
        <section className="result-card result-card-error">
          <h2>Planning failed</h2>
          <p>
            {finalDecision?.outcome ?? `Run finished with status "${run.status}" but no candidates were recorded.`}
          </p>
        </section>
      </div>
    );
  }

  const round1 = run.candidates.filter((c) => c.round === 1);
  const round2 = run.candidates.filter((c) => c.round === 2);
  const roundsRun = round2.length > 0 ? 2 : 1;
  const indexOf = (c: Candidate) => run.candidates.indexOf(c) + 1;
  const plottable = run.candidates.some((c) => c.status === "succeeded");

  return (
    <div className="results">
      {planDecision && <PlanCard decision={planDecision} candidateCount={round1.length} />}
      <RoundSection title="Round 1 experiments" candidates={round1} indexOf={indexOf} />

      {roundTwoDecision && <RoundTransitionCard decision={roundTwoDecision} round2Count={round2.length} />}
      <RoundSection
        title="Round 2 experiments"
        subtitle="Targeted follow-up proposed after seeing Round 1's real measurements."
        candidates={round2}
        indexOf={indexOf}
      />

      {plottable && (
        <section className="result-card">
          <h2>Pareto frontier</h2>
          <ParetoChart candidates={run.candidates} />
        </section>
      )}

      <SummaryCard summary={run.optimization_summary} roundsRun={roundsRun} />

      {winner ? (
        <RecommendationCard candidate={winner} decision={finalDecision} objective={run.optimization_preferences.objective} />
      ) : (
        <NoWinnerCard run={run} decision={finalDecision} />
      )}

      <ComparisonTable run={run} />

      <DecisionLedger decisions={run.decisions} />
    </div>
  );
}
