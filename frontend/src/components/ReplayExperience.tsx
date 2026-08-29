import { useEffect, useState } from "react";
import type { Candidate, RunDetail } from "../lib/api";
import { computeBeforeAfter, findDecision, isRound1OnlyParetoOptimal } from "../lib/replay";
import { RoundSection } from "./RoundSection";
import { RoundLearningPanel } from "./RoundLearningPanel";
import { RoundTransitionCard } from "./RoundTransitionCard";
import { LifecycleStepper } from "./LifecycleStepper";

/**
 * Stages an already-known, already-captured RunDetail (real or synthetic —
 * see lib/fixtures.ts) as a paced investigation, instead of dumping the
 * full result on screen at once. Every fact shown is read straight off the
 * fixture's real fields; nothing here is computed live "as if" slicing or
 * reasoning were actually happening — only the *reveal timing* is
 * animated. See the persistent banner (rendered by the parent, App.tsx)
 * for the required "recorded real run, replaying captured events" label.
 */

const SCENES = [
  "constraints",
  "plan-r1",
  "reveal-r1",
  "r1-frontier",
  "r1-learning",
  "decision-r2",
  "reveal-r2",
  "combined-frontier",
  "before-after",
] as const;
type Scene = (typeof SCENES)[number];

const SCENE_DURATION_MS: Partial<Record<Scene, number>> = {
  constraints: 1400,
  "plan-r1": 1800,
  "r1-frontier": 2200,
  "r1-learning": 3200,
  "decision-r2": 2200,
  "combined-frontier": 2800,
  "before-after": 2600,
};
const REVEAL_INTERVAL_MS = 550;

// Maps each real reveal scene onto the shared 6-stage lifecycle shown by
// LifecycleStepper (Plan / Slice candidates / Evaluate / Replan / Slice
// follow-up / Decide) — same labels AgentPipeline uses in live mode, so
// the two modes read as one consistent mental model. When a run genuinely
// has no Round 2 candidates (stopped, unavailable, or never adaptive),
// "Slice follow-up" is skipped rather than shown as reached — nothing was
// actually sliced in a follow-up round.
function stageForScene(scene: Scene, hasRound2: boolean): number {
  const base: Record<Scene, number> = {
    constraints: 0,
    "plan-r1": 0,
    "reveal-r1": 1,
    "r1-frontier": 2,
    "r1-learning": 2,
    "decision-r2": 3,
    "reveal-r2": hasRound2 ? 4 : 5,
    "combined-frontier": 5,
    "before-after": 5,
  };
  return base[scene];
}

function feasibleCountLabel(revealed: Candidate[]) {
  return `${revealed.filter((c) => c.is_feasible).length} / ${revealed.length || "8"} feasible`;
}

export function ReplayExperience({ run, onComplete }: { run: RunDetail; onComplete: () => void }) {
  const [sceneIndex, setSceneIndex] = useState(0);
  const [revealedR1, setRevealedR1] = useState(0);
  const [revealedR2, setRevealedR2] = useState(0);

  const round1 = run.candidates.filter((c) => c.round === 1);
  const round2 = run.candidates.filter((c) => c.round === 2);
  const finalFrontier = run.candidates.filter((c) => c.is_pareto_optimal);
  const planDecision = findDecision(run, ["plan_initial_candidates"]);
  const roundTwoDecision = findDecision(run, ["continue_optimization", "stop_optimization", "round_two_unavailable"]);
  const indexOf = (c: Candidate) => run.candidates.indexOf(c) + 1;
  const scene: Scene = SCENES[sceneIndex];

  useEffect(() => {
    if (sceneIndex >= SCENES.length) {
      onComplete();
      return;
    }

    if (scene === "reveal-r1" && round1.length > 0) {
      if (revealedR1 < round1.length) {
        const t = setTimeout(() => setRevealedR1((n) => n + 1), REVEAL_INTERVAL_MS);
        return () => clearTimeout(t);
      }
      const t = setTimeout(() => setSceneIndex((i) => i + 1), 700);
      return () => clearTimeout(t);
    }

    if (scene === "reveal-r2" && round2.length > 0) {
      if (revealedR2 < round2.length) {
        const t = setTimeout(() => setRevealedR2((n) => n + 1), REVEAL_INTERVAL_MS);
        return () => clearTimeout(t);
      }
      const t = setTimeout(() => setSceneIndex((i) => i + 1), 700);
      return () => clearTimeout(t);
    }

    const duration = SCENE_DURATION_MS[scene] ?? 1500;
    const t = setTimeout(() => setSceneIndex((i) => i + 1), duration);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneIndex, revealedR1, revealedR2]);

  const visibleRound1 = round1.slice(0, scene === "reveal-r1" ? revealedR1 : round1.length);
  const visibleRound2 = round2.slice(0, scene === "reveal-r2" ? revealedR2 : round2.length);
  const showRound1Section = sceneIndex >= SCENES.indexOf("reveal-r1");
  const showR1Frontier = sceneIndex >= SCENES.indexOf("r1-frontier");
  const showLearning = sceneIndex >= SCENES.indexOf("r1-learning");
  const showDecisionR2 = sceneIndex >= SCENES.indexOf("decision-r2");
  const showRound2Section = sceneIndex >= SCENES.indexOf("reveal-r2");
  const showCombinedFrontier = sceneIndex >= SCENES.indexOf("combined-frontier");
  const showBeforeAfter = sceneIndex >= SCENES.indexOf("before-after");

  const round1OnlyFrontier = round1.filter(isRound1OnlyParetoOptimal);
  const beforeAfter = computeBeforeAfter(round1, round2, finalFrontier);

  return (
    <div className="replay-experience">
      <LifecycleStepper currentIndex={stageForScene(scene, round2.length > 0)} />

      <div className="replay-status-line" aria-live="polite">
        <span className="replay-status-dot" />
        {scene === "constraints" && "Analyzing manufacturing constraints…"}
        {scene === "plan-r1" && "Gemini planning Round 1 experiments…"}
        {scene === "reveal-r1" && `Running PrusaSlicer measurements — ${feasibleCountLabel(visibleRound1)}`}
        {scene === "r1-frontier" && "Identifying the Round 1 Pareto frontier…"}
        {scene === "r1-learning" && "Evaluating Round 1 results…"}
        {scene === "decision-r2" && "Agent decision: planning Round 2…"}
        {scene === "reveal-r2" && `Running Round 2 measurements — ${feasibleCountLabel(visibleRound2)}`}
        {scene === "combined-frontier" && "Recomputing the combined Pareto frontier…"}
        {scene === "before-after" && "Summarizing the adaptive search…"}
      </div>

      {sceneIndex >= SCENES.indexOf("plan-r1") && planDecision && (
        <section className="result-card">
          <h2>Round 1 — experiment plan</h2>
          <p className="decision-observation">Gemini proposed {round1.length} experiments.</p>
        </section>
      )}

      {showRound1Section && (
        <RoundSection title="Round 1 experiments" candidates={visibleRound1} indexOf={indexOf} animateIn />
      )}

      {showR1Frontier && round1OnlyFrontier.length > 0 && (
        <section className="result-card">
          <h2>Round 1 Pareto frontier</h2>
          <p className="round-subtitle">
            {round1OnlyFrontier.length} of {round1.filter((c) => c.is_feasible).length} feasible Round 1 candidate
            {round1OnlyFrontier.length === 1 ? " is" : "s are"} non-dominated so far.
          </p>
          <RoundSection title="" candidates={round1OnlyFrontier} indexOf={indexOf} />
        </section>
      )}

      {showLearning && <RoundLearningPanel round1={round1} round2={round2} />}

      {showDecisionR2 && roundTwoDecision && (
        <RoundTransitionCard decision={roundTwoDecision} round2Count={round2.length} />
      )}

      {showRound2Section && (
        <RoundSection
          title="Round 2 experiments"
          subtitle="Targeted follow-up proposed after seeing Round 1's real measurements."
          candidates={visibleRound2}
          indexOf={indexOf}
          animateIn
        />
      )}

      {showCombinedFrontier && (
        <section className="result-card">
          <h2>Combined Pareto frontier</h2>
          <p className="round-subtitle">{finalFrontier.length} configurations remain non-dominated across both rounds.</p>
          <ul className="candidate-grid">
            {[...round1, ...round2]
              .filter((c) => c.is_feasible)
              .map((c) => (
                <li key={c.id} className={`frontier-dot-row ${c.is_pareto_optimal ? "frontier-dot-active" : "frontier-dot-dominated"}`}>
                  <span className="frontier-dot" />
                  round {c.round} — {c.layer_height}mm / {c.infill_percent}% / {c.perimeter_count}p
                  <span className="frontier-dot-status">{c.is_pareto_optimal ? "Pareto-optimal" : "dominated"}</span>
                </li>
              ))}
          </ul>
        </section>
      )}

      {showBeforeAfter && (
        <section className="result-card before-after-card">
          <div className="before-after-col">
            <span className="before-after-eyebrow">Round 1</span>
            <span className="before-after-value">{beforeAfter.round1FeasiblePercent}%</span>
            <span className="before-after-label">feasible</span>
          </div>
          <div className="before-after-arrow">→</div>
          <div className="before-after-col">
            <span className="before-after-eyebrow">Round 2</span>
            <span className="before-after-value">{beforeAfter.round2FeasiblePercent}%</span>
            <span className="before-after-label">feasible</span>
          </div>
          <div className="before-after-col before-after-col-highlight">
            <span className="before-after-eyebrow">Final Pareto frontier</span>
            <span className="before-after-value">{beforeAfter.finalFrontierFromRound2Percent}%</span>
            <span className="before-after-label">discovered in Round 2</span>
          </div>
        </section>
      )}

      <button type="button" className="secondary-button replay-skip-button" onClick={onComplete}>
        Skip to final result
      </button>
    </div>
  );
}
