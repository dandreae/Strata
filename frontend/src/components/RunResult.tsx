import type { Candidate, Decision, OptimizationSummary, RunDetail } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";
import { ParetoChart } from "./ParetoChart";
import { RoundSection } from "./RoundSection";
import { RecommendationCard } from "./RecommendationCard";
import { DecisionLedger } from "./DecisionLedger";

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
 * before any slicing happened. */
function PlanCard({ decision }: { decision: Decision }) {
  const strategy = decision.evidence[0];
  return (
    <section className="result-card">
      <h2>Round 1 — experiment plan</h2>
      <p className="decision-observation">{decision.observation}</p>
      {strategy && (
        <>
          <p className="decision-evidence-heading">Strategy</p>
          <p className="decision-outcome">“{strategy}”</p>
        </>
      )}
    </section>
  );
}

/** The pivot moment: the agent used Round 1's real measurements to decide
 * whether a second, targeted round is worth running. Represented exactly
 * as the backend recorded it — including the case where Round 2 planning
 * itself failed (Round 1's results still stand). */
function RoundTwoDecisionCard({ decision }: { decision: Decision }) {
  const reasoning = decision.evidence[0];

  if (decision.selected_action === "round_two_unavailable") {
    return (
      <section className="result-card round-transition-card round-transition-unavailable">
        <span className="chip chip-caution">Round 2 unavailable</span>
        <p className="decision-observation">{decision.observation}</p>
        <p className="decision-outcome">Round 1's measured results are still used — nothing here is discarded.</p>
      </section>
    );
  }

  const continuing = decision.selected_action === "continue_optimization";
  return (
    <section className={`result-card round-transition-card ${continuing ? "round-transition-continue" : "round-transition-stop"}`}>
      <span className={`chip ${continuing ? "chip-pareto" : "chip-winner"}`}>
        Gemini evaluated the measured Round 1 results → {continuing ? "Continue search" : "Stop"}
      </span>
      {reasoning && <p className="decision-outcome">“{reasoning}”</p>}
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
    return (
      <section className="result-card result-card-pending">
        <h2>Multiple equally good options</h2>
        <p>
          {decision?.outcome ??
            "Several feasible candidates are mutually non-dominated and no optimization priority resolves the tradeoff."}
        </p>
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
      {planDecision && <PlanCard decision={planDecision} />}
      <RoundSection title="Round 1 experiments" candidates={round1} indexOf={indexOf} />

      {roundTwoDecision && <RoundTwoDecisionCard decision={roundTwoDecision} />}
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
