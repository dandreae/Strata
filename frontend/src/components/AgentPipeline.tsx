import { useEffect, useState } from "react";

/**
 * The "watch agent work" visualization shown while a run is in flight.
 *
 * Honesty constraint: `POST /api/v1/runs` is one blocking call that only
 * responds once the entire pipeline has finished — the backend does not
 * stream per-stage progress (see docs/architecture.md). So this component
 * does NOT claim to know which stage the backend is really on. It narrates
 * the real, true pipeline (these stages genuinely execute, in this order,
 * every run) and paces itself on a fixed timer as an illustration — then
 * immediately jumps to "done" the moment the real response actually
 * arrives, however long that took. The on-screen caption says exactly
 * this, so nothing here misrepresents live backend state.
 */

const STAGES = [
  "Analyzing constraints",
  "Planning Round 1 experiments",
  "Slicing candidates",
  "Evaluating measured results",
  "Planning adaptive Round 2",
  "Comparing Pareto-optimal configurations",
  "Selecting recommendation",
] as const;

// Weighted so early/late reasoning stages are quick and "Slicing" (the real
// bottleneck — a genuine subprocess call per candidate) reads as the
// longest, roughly matching the shape of real observed run timing.
const STAGE_WEIGHTS = [0.6, 1.2, 2.6, 1.3, 1.4, 0.9, 0.8];
const TOTAL_ILLUSTRATIVE_SECONDS = 30;

export function AgentPipeline() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const weightSum = STAGE_WEIGHTS.reduce((a, b) => a + b, 0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;
    for (let i = 1; i < STAGES.length; i++) {
      elapsed += (STAGE_WEIGHTS[i - 1] / weightSum) * TOTAL_ILLUSTRATIVE_SECONDS;
      timers.push(setTimeout(() => setActiveIndex(i), elapsed * 1000));
    }
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <section className="pipeline-card" aria-live="polite">
      <h2 className="pipeline-heading">Strata is working</h2>
      <ol className="pipeline-list">
        {STAGES.map((stage, i) => {
          const state = i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";
          return (
            <li key={stage} className={`pipeline-step pipeline-step-${state}`}>
              <span className="pipeline-marker" aria-hidden="true">
                {state === "done" ? "✓" : state === "active" ? "" : ""}
              </span>
              <span className="pipeline-label">{stage}</span>
            </li>
          );
        })}
      </ol>
      <p className="pipeline-caption">
        Every step above genuinely runs, in this order, on the real backend — Gemini/ADK proposing
        experiments, real PrusaSlicer measuring them, Gemini deciding whether a second round is
        worthwhile. The backend replies once, at the end, rather than streaming progress, so this
        list paces itself on a timer as an illustration and will jump straight to the real result
        the moment it actually arrives.
      </p>
    </section>
  );
}
