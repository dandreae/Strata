import type { Candidate, Decision, Objective } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

const OBJECTIVE_TEXT: Record<Objective, string> = {
  minimize_material: "minimizing material usage",
  minimize_time: "minimizing print time",
  balanced: "balancing print time and material usage",
};

/** The prominent final-answer card. Every manufacturing number here is
 * explicitly labeled as PrusaSlicer output, never a Gemini prediction —
 * Gemini proposes configurations to try, it never estimates their
 * print time or material use (see docs/architecture.md §3). */
export function RecommendationCard({
  candidate,
  decision,
  objective,
}: {
  candidate: Candidate;
  decision: Decision | undefined;
  objective: Objective;
}) {
  return (
    <section className="result-card recommendation-card">
      <span className="selected-badge">Recommended configuration</span>

      <div className="recommendation-metrics">
        <div className="recommendation-metric">
          <span className="recommendation-metric-value">{formatDuration(candidate.print_time_seconds ?? 0)}</span>
          <span className="recommendation-metric-label">Print time</span>
        </div>
        <div className="recommendation-metric">
          <span className="recommendation-metric-value">{formatGrams(candidate.filament_grams ?? 0)}</span>
          <span className="recommendation-metric-label">Material</span>
        </div>
      </div>
      <p className="measured-tag">Measured by PrusaSlicer — not predicted by Gemini</p>

      <dl className="spec-grid recommendation-spec">
        <dt>Layer height</dt>
        <dd>{candidate.layer_height.toFixed(2)} mm</dd>
        <dt>Infill</dt>
        <dd>{candidate.infill_percent}%</dd>
        <dt>Perimeters</dt>
        <dd>{candidate.perimeter_count}</dd>
        <dt>Supports</dt>
        <dd>{candidate.supports_enabled ? "On" : "Off"}</dd>
        <dt>Experiment round</dt>
        <dd>Round {candidate.round}</dd>
      </dl>

      <p className="recommendation-reason">
        Chosen from every Pareto-optimal candidate tested, {OBJECTIVE_TEXT[objective]} as requested.
        {decision?.evidence[0] && <> {decision.evidence[0]}</>}
      </p>

      {candidate.constraint_checks.length > 0 && (
        <ul className="requirement-list">
          {candidate.constraint_checks.map((check) => (
            <li key={check.key} className={check.passed ? "requirement requirement-pass" : "requirement requirement-fail"}>
              <span className="requirement-mark">{check.passed ? "✓" : "✕"}</span>
              <span className="requirement-text">
                <span className="requirement-label">{check.label} within limit</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
