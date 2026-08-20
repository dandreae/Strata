import type { Candidate } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

const STATUS_TEXT: Record<Candidate["status"], string> = {
  succeeded: "Sliced",
  failed: "Slicing failed",
  pending: "Pending",
  slicing: "Slicing…",
};

function CandidateCard({ candidate, index }: { candidate: Candidate; index: number }) {
  const badges: string[] = [];
  if (candidate.is_selected) badges.push("selected");
  else if (candidate.is_pareto_optimal) badges.push("pareto");
  else if (candidate.status === "succeeded" && !candidate.is_feasible) badges.push("infeasible");

  return (
    <li className={`candidate-card ${badges.map((b) => `candidate-card-${b}`).join(" ")}`}>
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
        <dl className="candidate-card-metrics">
          <dt>Print time</dt>
          <dd>{candidate.print_time_seconds !== null ? formatDuration(candidate.print_time_seconds) : "—"}</dd>
          <dt>Material</dt>
          <dd>{candidate.filament_grams !== null ? formatGrams(candidate.filament_grams) : "—"}</dd>
        </dl>
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
}: {
  title: string;
  subtitle?: string;
  candidates: Candidate[];
  indexOf: (candidate: Candidate) => number;
}) {
  if (candidates.length === 0) return null;

  return (
    <section className="result-card">
      <h2>{title}</h2>
      {subtitle && <p className="round-subtitle">{subtitle}</p>}
      <ul className="candidate-grid">
        {candidates.map((c) => (
          <CandidateCard key={c.id} candidate={c} index={indexOf(c)} />
        ))}
      </ul>
    </section>
  );
}
