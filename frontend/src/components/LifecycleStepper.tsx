/**
 * Persistent, compact progress indicator for the optimization lifecycle —
 * shown identically in both live mode (AgentPipeline, paced on an honest
 * illustrative timer since the backend doesn't stream progress) and
 * fixture/replay mode (ReplayExperience, driven by real reveal progress),
 * so a judge sees one consistent mental model regardless of which is
 * running. Purely presentational: callers compute `currentIndex` from
 * their own existing state — this component invents no new state, no new
 * backend calls, nothing beyond rendering six fixed labels.
 *
 * A run without a Round 2 (single-round deterministic mode, or a run that
 * completes/fails before ever reaching that decision) simply never
 * advances `currentIndex` past "Evaluate" into "Replan"/"Slice follow-up"
 * — those stay visibly pending rather than being faked as reached.
 */
const STAGES = ["Plan", "Slice candidates", "Evaluate", "Replan", "Slice follow-up", "Decide"] as const;

export function LifecycleStepper({ currentIndex }: { currentIndex: number }) {
  return (
    <ol className="lifecycle-stepper" aria-label="Optimization lifecycle progress">
      {STAGES.map((stage, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "pending";
        return (
          <li key={stage} className={`lifecycle-step lifecycle-step-${state}`}>
            <span className="lifecycle-step-marker" aria-hidden="true">
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className="lifecycle-step-label">{stage}</span>
          </li>
        );
      })}
    </ol>
  );
}
