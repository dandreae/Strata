import { useEffect, useState } from "react";
import { LifecycleStepper } from "./LifecycleStepper";

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
 *
 * Stage names match LifecycleStepper exactly (Plan / Slice candidates /
 * Evaluate / Replan / Slice follow-up / Decide) so live mode and replay
 * mode read as the same mental model.
 */

// Weighted so "Slice candidates" and "Slice follow-up" (the real
// bottleneck — genuine subprocess calls per candidate) read as the
// longest, roughly matching the shape of real observed run timing.
const STAGE_WEIGHTS = [1.8, 2.6, 1.3, 1.4, 2.0, 1.7];
const TOTAL_ILLUSTRATIVE_SECONDS = 30;

export function AgentPipeline() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const weightSum = STAGE_WEIGHTS.reduce((a, b) => a + b, 0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;
    for (let i = 1; i < STAGE_WEIGHTS.length; i++) {
      elapsed += (STAGE_WEIGHTS[i - 1] / weightSum) * TOTAL_ILLUSTRATIVE_SECONDS;
      timers.push(setTimeout(() => setActiveIndex(i), elapsed * 1000));
    }
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <section className="pipeline-card" aria-live="polite">
      <h2 className="pipeline-heading">Strata is working</h2>
      <LifecycleStepper currentIndex={activeIndex} />
      <p className="pipeline-caption">
        Gemini proposes experiments, real PrusaSlicer measures them, Gemini reviews the results and
        decides whether a second round is worth it. The backend replies once, at the end — this
        pacing is an illustration and will jump straight to the real result the moment it arrives.
      </p>
    </section>
  );
}
