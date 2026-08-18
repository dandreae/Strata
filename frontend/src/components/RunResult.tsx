import type { Candidate, ConstraintCheck, Decision, OptimizationSummary, RunDetail } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

function formatCheckValue(value: number | null, unit: string): string {
  if (value === null) return "unavailable";
  return unit === "s" ? formatDuration(value) : formatGrams(value);
}

function candidateLabel(run: RunDetail, candidate: Candidate): string {
  return `Candidate #${run.candidates.indexOf(candidate) + 1}`;
}

function SummaryCard({ summary }: { summary: OptimizationSummary }) {
  return (
    <section className="result-card">
      <h2>Optimization summary</h2>
      <p className="summary-line">
        <strong>{summary.candidates_tested}</strong> candidates tested &nbsp;·&nbsp; <strong>{summary.succeeded}</strong>{" "}
        sliced successfully &nbsp;·&nbsp; <strong>{summary.feasible}</strong> feasible &nbsp;·&nbsp;{" "}
        <strong>{summary.pareto_optimal}</strong> Pareto optimal
      </p>
    </section>
  );
}

function CandidateSpec({ candidate }: { candidate: Candidate }) {
  return (
    <dl className="spec-grid">
      <dt>Layer height</dt>
      <dd>{candidate.layer_height.toFixed(2)} mm</dd>
      <dt>Infill</dt>
      <dd>{candidate.infill_percent}%</dd>
      <dt>Supports</dt>
      <dd>{candidate.supports_enabled ? "On" : "Off"}</dd>
      <dt>Perimeters</dt>
      <dd>{candidate.perimeter_count}</dd>
      <dt>Orientation</dt>
      <dd>
        {candidate.orientation_x}° / {candidate.orientation_y}° / {candidate.orientation_z}°
      </dd>
    </dl>
  );
}

function RequirementRow({ check }: { check: ConstraintCheck }) {
  return (
    <li className={check.passed ? "requirement requirement-pass" : "requirement requirement-fail"}>
      <span className="requirement-mark">{check.passed ? "✓" : "✕"}</span>
      <span className="requirement-text">
        <span className="requirement-label">
          {check.label} ≤ {formatCheckValue(check.limit, check.unit)}
        </span>
        <span className="requirement-actual">Actual: {formatCheckValue(check.actual, check.unit)}</span>
      </span>
    </li>
  );
}

/** What the planner (deterministic or Gemini+ADK) proposed, before any
 * slicing happened — see DecisionRecord.selected_action="plan_initial_candidates". */
function PlanCard({ decision }: { decision: Decision }) {
  // planning_summary is always the first evidence line (see
  // app/services/orchestrator.py::_planning_decision) — displayed as-is,
  // never re-derived or parsed on the frontend.
  const strategy = decision.evidence[0];
  return (
    <section className="result-card">
      <h2>Experiment plan</h2>
      <p className="decision-observation">{decision.observation}</p>
      {strategy && (
        <>
          <p className="decision-evidence-heading">Strategy</p>
          <p className="decision-outcome">{strategy}</p>
        </>
      )}
    </section>
  );
}

/** The winning candidate, shown prominently and labeled SELECTED. */
function SelectedCandidateCard({ run, candidate }: { run: RunDetail; candidate: Candidate }) {
  return (
    <section className="result-card result-card-selected">
      <span className="selected-badge">SELECTED</span>
      <h2>{candidateLabel(run, candidate)}</h2>
      <CandidateSpec candidate={candidate} />

      <dl className="spec-grid metrics-grid">
        <dt>Print time</dt>
        <dd className="metric-value">
          {candidate.print_time_seconds !== null ? formatDuration(candidate.print_time_seconds) : "unavailable"}
        </dd>
        <dt>Material</dt>
        <dd className="metric-value">
          {candidate.filament_grams !== null ? formatGrams(candidate.filament_grams) : "unavailable"}
        </dd>
      </dl>

      {candidate.constraint_checks.length > 0 && (
        <ul className="requirement-list">
          {candidate.constraint_checks.map((check) => (
            <RequirementRow key={check.key} check={check} />
          ))}
        </ul>
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
        <h2>Slicing did not complete</h2>
        <p>{firstFailure ?? decision?.outcome ?? "Slicing failed for an unknown reason."}</p>
      </section>
    );
  }

  if (run.status === "infeasible") {
    return (
      <section className="result-card result-card-error">
        <h2>No feasible candidate found</h2>
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
      <h2>Candidates tested</h2>
      <div className="comparison-scroll">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Candidate</th>
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

const DECISION_LABELS: Record<string, string> = {
  select_candidate: "CANDIDATE SELECTED",
  no_feasible_candidate: "NO FEASIBLE CANDIDATE",
  escalate_tradeoff: "TRADEOFF — INPUT NEEDED",
  abort_run: "RUN ABORTED",
  // Retained for older records created before this milestone.
  accept_candidate: "ACCEPT CANDIDATE",
  reject_candidate: "REJECT CANDIDATE",
};

const POSITIVE_ACTIONS = new Set(["select_candidate", "accept_candidate"]);

function DecisionCard({ decision }: { decision: Decision }) {
  const label = DECISION_LABELS[decision.selected_action] ?? decision.selected_action.toUpperCase();
  const tone = POSITIVE_ACTIONS.has(decision.selected_action) ? "decision-accept" : "decision-reject";

  return (
    <section className="result-card">
      <h2>Decision</h2>
      <p className={`decision-label ${tone}`}>{label}</p>
      <p className="decision-observation">{decision.observation}</p>
      {decision.outcome && <p className="decision-outcome">{decision.outcome}</p>}

      {decision.evidence.length > 0 && (
        <>
          <p className="decision-evidence-heading">Evidence</p>
          <ul className="evidence-list">
            {decision.evidence.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </>
      )}

      {decision.alternatives.length > 0 && (
        <>
          <p className="decision-evidence-heading">Other Pareto-optimal alternatives considered</p>
          <ul className="evidence-list">
            {decision.alternatives.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </>
      )}

      <p className="decision-human">Human input required: {decision.requires_human ? "Yes" : "No"}</p>
    </section>
  );
}

export function RunResult({ run }: { run: RunDetail }) {
  // Two decisions are recorded per run: the planning decision (always
  // selected_action="plan_initial_candidates", written before any slicing)
  // and the final one (select_candidate / no_feasible_candidate /
  // escalate_tradeoff / abort_run). Found by content, not array position,
  // so this doesn't depend on save order.
  const planDecision = run.decisions.find((d) => d.selected_action === "plan_initial_candidates");
  const finalDecision = run.decisions.find((d) => d.selected_action !== "plan_initial_candidates");
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

  return (
    <div className="results">
      {planDecision && <PlanCard decision={planDecision} />}
      <SummaryCard summary={run.optimization_summary} />
      {winner ? (
        <SelectedCandidateCard run={run} candidate={winner} />
      ) : (
        <NoWinnerCard run={run} decision={finalDecision} />
      )}
      <ComparisonTable run={run} />
      {finalDecision && <DecisionCard decision={finalDecision} />}
    </div>
  );
}
