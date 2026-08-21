import type { Candidate } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

const STATUS_TEXT: Record<Candidate["status"], string> = {
  succeeded: "Sliced",
  failed: "Slicing failed",
  pending: "Pending",
  slicing: "Slicing…",
};

function formatCheckValue(actual: number | null, unit: string): string {
  if (actual === null) return "—";
  return unit === "s" ? formatDuration(actual) : formatGrams(actual);
}

/** The deterministic comparison a judge can verify at a glance — every
 * number here is the backend's own `constraint_checks[].actual`/`.limit`,
 * just formatted, never recomputed. */
function ConstraintMathLine({ candidate }: { candidate: Candidate }) {
  const failing = candidate.constraint_checks.filter((c) => !c.passed);
  if (failing.length === 0) return null;
  return (
    <p className="constraint-math">
      {failing.map((c, i) => (
        <span key={c.key} className="constraint-math-item">
          {i > 0 && " · "}
          {formatCheckValue(c.actual, c.unit)} &gt; {formatCheckValue(c.limit, c.unit)} → rejected
        </span>
      ))}
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
          <span className="chip chip-infeasible">Exceeds constraints</span>
        )}
      </div>

      <dl className="candidate-card-spec">
        <dt>Layer</dt>
        <dd>{candidate.layer_height.toFixed(2)}mm</dd>
        <dt>Infill</dt>
        <dd>{candidate.infill_percent}%</dd>
        <dt>Perimeters</dt>
        <dd>{candidate.perimeter_count}</dd>
      </dl>

      {candidate.status === "succeeded" ? (
        <>
          <dl className="candidate-card-metrics">
            <dt>Print time</dt>
            <dd>{candidate.print_time_seconds !== null ? formatDuration(candidate.print_time_seconds) : "—"}</dd>
            <dt>Material</dt>
            <dd>{candidate.filament_grams !== null ? formatGrams(candidate.filament_grams) : "—"}</dd>
          </dl>
          <ConstraintMathLine candidate={candidate} />
        </>
      ) : (
        <p className="candidate-card-status">{STATUS_TEXT[candidate.status]}</p>
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
