import type { Candidate, ConstraintCheck, Decision, RunDetail } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

function formatCheckValue(value: number | null, unit: string): string {
  if (value === null) return "unavailable";
  return unit === "s" ? formatDuration(value) : formatGrams(value);
}

function CandidateSpec({ candidate }: { candidate: Candidate }) {
  return (
    <section className="result-card">
      <h2>Candidate #1</h2>
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
    </section>
  );
}

function Metrics({ candidate }: { candidate: Candidate }) {
  if (candidate.status !== "succeeded") return null;
  return (
    <section className="result-card">
      <h2>Real PrusaSlicer results</h2>
      <dl className="spec-grid">
        <dt>Estimated print time</dt>
        <dd className="metric-value">
          {candidate.print_time_seconds !== null ? formatDuration(candidate.print_time_seconds) : "unavailable"}
        </dd>
        <dt>Filament</dt>
        <dd className="metric-value">
          {candidate.filament_grams !== null ? formatGrams(candidate.filament_grams) : "unavailable"}
        </dd>
      </dl>
    </section>
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

function Requirements({ candidate }: { candidate: Candidate }) {
  if (candidate.constraint_checks.length === 0) return null;
  return (
    <section className="result-card">
      <h2>Requirements</h2>
      <ul className="requirement-list">
        {candidate.constraint_checks.map((check) => (
          <RequirementRow key={check.key} check={check} />
        ))}
      </ul>
    </section>
  );
}

const DECISION_LABELS: Record<string, string> = {
  accept_candidate: "ACCEPT CANDIDATE",
  reject_candidate: "REJECT CANDIDATE",
  abort_run: "RUN ABORTED",
};

function DecisionCard({ decision }: { decision: Decision }) {
  const label = DECISION_LABELS[decision.selected_action] ?? decision.selected_action.toUpperCase();
  const tone = decision.selected_action === "accept_candidate" ? "decision-accept" : "decision-reject";

  return (
    <section className="result-card">
      <h2>Decision</h2>
      <p className={`decision-label ${tone}`}>{label}</p>
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

      <p className="decision-human">Human input required: {decision.requires_human ? "Yes" : "No"}</p>
    </section>
  );
}

/** run.status === "failed" — a technical slicing/infrastructure failure,
 * distinct from a candidate being rejected for violating constraints. */
function FailureCard({ candidate, decision }: { candidate: Candidate; decision: Decision | undefined }) {
  return (
    <section className="result-card result-card-error">
      <h2>Slicing did not complete</h2>
      <p>{candidate.failure_reason ?? decision?.outcome ?? "Slicing failed for an unknown reason."}</p>
    </section>
  );
}

export function RunResult({ run }: { run: RunDetail }) {
  const candidate = run.candidates[0];
  const decision = run.decisions[0];

  if (!candidate) {
    return (
      <section className="result-card">
        <p>Run finished with status "{run.status}" but no candidate was recorded.</p>
      </section>
    );
  }

  if (run.status === "failed") {
    return (
      <div className="results">
        <CandidateSpec candidate={candidate} />
        <FailureCard candidate={candidate} decision={decision} />
      </div>
    );
  }

  return (
    <div className="results">
      <CandidateSpec candidate={candidate} />
      <Metrics candidate={candidate} />
      <Requirements candidate={candidate} />
      {decision && <DecisionCard decision={decision} />}
    </div>
  );
}
