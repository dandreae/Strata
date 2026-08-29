import type { Candidate } from "../lib/api";
import { formatDuration, formatDurationCompact, formatGrams } from "../lib/duration";

const STATUS_TEXT: Record<Candidate["status"], string> = {
  succeeded: "Sliced",
  failed: "Slicing failed",
  pending: "Pending",
  slicing: "Slicing…",
};

function formatLimitCompact(limit: number, unit: string): string {
  return unit === "s" ? formatDurationCompact(limit) : formatGrams(limit);
}

/** Compact, scannable rejection reason — e.g. "Rejected · Print time > 45m"
 * — naming which constraint(s) failed rather than repeating both sides of
 * the comparison. Every value here is still the backend's own
 * `constraint_checks[].limit`, just formatted differently; nothing is
 * recomputed. The full actual-vs-limit numbers remain visible in the
 * comparison table and decision ledger for anyone who wants them. */
function RejectionFooter({ candidate }: { candidate: Candidate }) {
  const failing = candidate.constraint_checks.filter((c) => !c.passed);
  if (failing.length === 0) return null;
  return (
    <p className="constraint-math">
      Rejected · {failing.map((c) => `${c.label} > ${formatLimitCompact(c.limit, c.unit)}`).join(" · ")}
    </p>
  );
}

function CandidateCard({ candidate, index, animateIn }: { candidate: Candidate; index: number; animateIn?: boolean }) {
  const badges: string[] = [];
  if (candidate.is_selected) badges.push("selected");
  else if (candidate.is_pareto_optimal) badges.push("pareto");
  else if (candidate.status === "succeeded" && !candidate.is_feasible) badges.push("infeasible");

  return (
    <li className={`candidate-card ${animateIn ? "candidate-card-enter" : ""} ${badges.map((b) => `candidate-card-${b}`).join(" ")}`}>
      <div className="candidate-card-head">
        <span className="candidate-card-index">#{index}</span>
        {candidate.is_selected && <span className="chip chip-winner">Selected</span>}
        {!candidate.is_selected && candidate.is_pareto_optimal && <span className="chip chip-pareto">Pareto-optimal</span>}
        {!candidate.is_selected && candidate.status === "succeeded" && !candidate.is_feasible && (
          <span className="chip chip-infeasible">Rejected</span>
        )}
      </div>

      {candidate.status === "succeeded" ? (
        <>
          {/* Print time / material are the headline numbers — what a judge
              should read first, before the configuration that produced them. */}
          <dl className="candidate-card-metrics">
            <dt>Print time</dt>
            <dd>{candidate.print_time_seconds !== null ? formatDuration(candidate.print_time_seconds) : "—"}</dd>
            <dt>Material</dt>
            <dd>{candidate.filament_grams !== null ? formatGrams(candidate.filament_grams) : "—"}</dd>
          </dl>

          <dl className="candidate-card-spec">
            <dt>Layer</dt>
            <dd>{candidate.layer_height.toFixed(2)}mm</dd>
            <dt>Infill</dt>
            <dd>{candidate.infill_percent}%</dd>
            <dt>Perimeters</dt>
            <dd>{candidate.perimeter_count}</dd>
          </dl>

          <RejectionFooter candidate={candidate} />
        </>
      ) : (
        <>
          <dl className="candidate-card-spec">
            <dt>Layer</dt>
            <dd>{candidate.layer_height.toFixed(2)}mm</dd>
            <dt>Infill</dt>
            <dd>{candidate.infill_percent}%</dd>
            <dt>Perimeters</dt>
            <dd>{candidate.perimeter_count}</dd>
          </dl>
          <p className="candidate-card-status">{STATUS_TEXT[candidate.status]}</p>
        </>
      )}
    </li>
  );
}

export function RoundSection({
  title,
  subtitle,
  candidates,
  indexOf,
  animateIn,
}: {
  title: string;
  subtitle?: string;
  candidates: Candidate[];
  indexOf: (candidate: Candidate) => number;
  animateIn?: boolean;
}) {
  if (candidates.length === 0) return null;

  return (
    <section className="result-card">
      <h2>{title}</h2>
      {subtitle && <p className="round-subtitle">{subtitle}</p>}
      <ul className="candidate-grid">
        {candidates.map((c) => (
          <CandidateCard key={c.id} candidate={c} index={indexOf(c)} animateIn={animateIn} />
        ))}
      </ul>
    </section>
  );
}
