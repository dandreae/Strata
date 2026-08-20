import type { Decision } from "../lib/api";

/** Every selected_action the backend actually emits (app/services/orchestrator.py)
 * — see docs/architecture.md §5. Labels only; never invents an action the
 * backend didn't record. */
const ACTION_LABELS: Record<string, string> = {
  plan_initial_candidates: "Round 1 planned",
  continue_optimization: "Round 2 — continue",
  stop_optimization: "Round 2 — stop",
  round_two_unavailable: "Round 2 unavailable",
  select_candidate: "Configuration selected",
  no_feasible_candidate: "No feasible candidate",
  escalate_tradeoff: "Tradeoff — human input needed",
  abort_run: "Run aborted",
};

const ACTION_TONE: Record<string, "good" | "bad" | "neutral"> = {
  plan_initial_candidates: "neutral",
  continue_optimization: "neutral",
  stop_optimization: "neutral",
  round_two_unavailable: "bad",
  select_candidate: "good",
  no_feasible_candidate: "bad",
  escalate_tradeoff: "bad",
  abort_run: "bad",
};

function DecisionEntry({ decision, index }: { decision: Decision; index: number }) {
  const label = ACTION_LABELS[decision.selected_action] ?? decision.selected_action.replace(/_/g, " ");
  const tone = ACTION_TONE[decision.selected_action] ?? "neutral";

  return (
    <li className="ledger-entry">
      <span className={`ledger-marker ledger-marker-${tone}`} aria-hidden="true">
        {index + 1}
      </span>
      <div className="ledger-entry-body">
        <p className={`ledger-action ledger-action-${tone}`}>{label}</p>
        <p className="decision-observation">{decision.observation}</p>

        {decision.evidence.length > 0 && (
          <ul className="evidence-list">
            {decision.evidence.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
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

        {decision.requires_human && <p className="ledger-human-flag">Flagged for human input</p>}
      </div>
    </li>
  );
}

/** Full, ordered decision timeline — the backend's actual audit trail, not
 * chain-of-thought. Collapsed by default (native <details>, no JS state) so
 * it doesn't compete with the headline results, but every decision the run
 * made is here for a judge who wants to dig in. */
export function DecisionLedger({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) return null;

  return (
    <details className="result-card ledger-card">
      <summary className="ledger-summary">
        Decision ledger / agent trace <span className="ledger-count">({decisions.length})</span>
      </summary>
      <ol className="ledger-list">
        {decisions.map((d, i) => (
          <DecisionEntry key={d.id} decision={d} index={i} />
        ))}
      </ol>
    </details>
  );
}
