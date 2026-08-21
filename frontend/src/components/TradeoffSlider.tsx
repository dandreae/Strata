import { useState } from "react";
import type { Candidate } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

/**
 * The human-in-the-loop moment: when the backend correctly refuses to pick
 * among genuinely non-dominated candidates (a real `escalate_tradeoff`
 * decision — see RunResult.tsx), this lets a person browse exactly that
 * real Pareto-optimal set. It never invents a new candidate, never
 * recomputes Pareto status, and never asserts a selection back to any
 * backend — it's a client-side viewer over the backend's own real frontier,
 * demonstrating the point: automate where evidence is sufficient, ask a
 * human only where the remaining choice is genuinely subjective.
 */
export function TradeoffSlider({ frontier }: { frontier: Candidate[] }) {
  const [index, setIndex] = useState(0);
  if (frontier.length === 0) return null;

  const selected = frontier[Math.min(index, frontier.length - 1)];

  return (
    <div className="tradeoff-slider">
      <div className="tradeoff-slider-labels">
        <span>◀ Faster</span>
        <span>Less material ▶</span>
      </div>
      <input
        type="range"
        min={0}
        max={frontier.length - 1}
        step={1}
        value={index}
        onChange={(e) => setIndex(Number(e.target.value))}
        className="tradeoff-slider-input"
        aria-label="Browse the Pareto-optimal configurations, from fastest to lowest material"
      />
      <div className="tradeoff-slider-ticks">
        {frontier.map((_, i) => (
          <span key={i} className={`tradeoff-tick ${i === index ? "tradeoff-tick-active" : ""}`} />
        ))}
      </div>

      <div className="tradeoff-preview">
        <div className="tradeoff-preview-metrics">
          <div>
            <span className="tradeoff-preview-value">{formatDuration(selected.print_time_seconds ?? 0)}</span>
            <span className="tradeoff-preview-label">Print time</span>
          </div>
          <div>
            <span className="tradeoff-preview-value">{formatGrams(selected.filament_grams ?? 0)}</span>
            <span className="tradeoff-preview-label">Material</span>
          </div>
        </div>
        <dl className="spec-grid tradeoff-preview-spec">
          <dt>Layer height</dt>
          <dd>{selected.layer_height.toFixed(2)} mm</dd>
          <dt>Infill</dt>
          <dd>{selected.infill_percent}%</dd>
          <dt>Perimeters</dt>
          <dd>{selected.perimeter_count}</dd>
        </dl>
      </div>
      <p className="tradeoff-note">
        All {frontier.length} options here are Pareto-optimal — none is objectively better than another on both
        axes. This is a viewer, not a re-run: Strata already determined this is the full real frontier.
      </p>
    </div>
  );
}
