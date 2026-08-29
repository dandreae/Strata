import { useId, useMemo } from "react";
import type { Candidate } from "../lib/api";
import { formatDuration, formatGrams } from "../lib/duration";

/**
 * Pareto frontier scatter: X = print time, Y = material usage, one dot per
 * successfully-sliced candidate. Status (tested / Pareto-optimal / selected)
 * comes straight from the backend's `is_pareto_optimal`/`is_selected` flags
 * — this component only plots those values, it never recomputes dominance
 * or selection itself (see app/optimization for the source of truth).
 */

const WIDTH = 640;
const HEIGHT = 360;
const MARGIN = { top: 24, right: 24, bottom: 48, left: 64 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;

/** Round a raw tick *step* up to a clean interval (1/2/5/10 × 10^n) so
 * gridlines land on readable values. Deliberately NOT used on the axis
 * extent itself — snapping the whole span to a "nice" number can overshoot
 * by nearly 2x at some magnitudes (e.g. a real 55-minute span snapping up
 * to 83 minutes), which defeats the point of a tight range. */
function niceStep(rawStep: number): number {
  if (rawStep <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const niceNormalized = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return niceNormalized * magnitude;
}

/** A tight-but-padded [min, max] axis range derived directly from the real
 * data — not always anchored at zero, so a cluster of candidates (e.g. all
 * between 1500-2500s) isn't crushed into a corner of the plot, and not
 * rounded out to a coarse "nice" bound either. Padding is proportional to
 * the real spread, with a floor so a near-constant value (or a single
 * candidate) still gets a sane range instead of a zero-width axis. */
function tightRange(values: number[]): { min: number; max: number } {
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const spread = dataMax - dataMin;
  const padding = Math.max(spread * 0.15, dataMax * 0.06, 1);
  return { min: Math.max(0, dataMin - padding), max: dataMax + padding };
}

/** Gridlines at a clean step size within [min, max] — ticks don't need to
 * span the full axis to a "nice" round number, only their spacing does. */
function ticksFor(min: number, max: number, count = 5): number[] {
  const step = niceStep((max - min) / count) || 1;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let t = start; t <= max + step * 0.001; t += step) ticks.push(Math.round(t * 100) / 100);
  return ticks;
}

function candidateLabel(c: Candidate): string {
  return `Round ${c.round} · ${c.layer_height.toFixed(2)}mm layer / ${c.infill_percent}% infill / ${c.perimeter_count} perimeters`;
}

export function ParetoChart({ candidates }: { candidates: Candidate[] }) {
  const gradientId = useId();
  const plotted = useMemo(
    () => candidates.filter((c) => c.status === "succeeded" && c.print_time_seconds !== null && c.filament_grams !== null),
    [candidates],
  );

  if (plotted.length === 0) {
    return null;
  }

  const timeRange = tightRange(plotted.map((c) => c.print_time_seconds!));
  const gramsRange = tightRange(plotted.map((c) => c.filament_grams!));
  const xTicks = ticksFor(timeRange.min, timeRange.max);
  const yTicks = ticksFor(gramsRange.min, gramsRange.max);

  const x = (seconds: number) =>
    MARGIN.left + ((seconds - timeRange.min) / (timeRange.max - timeRange.min || 1)) * PLOT_W;
  const y = (grams: number) =>
    MARGIN.top + PLOT_H - ((grams - gramsRange.min) / (gramsRange.max - gramsRange.min || 1)) * PLOT_H;

  // Render order: dominated first (bottom), Pareto next, selected winner
  // last (top) — so the winner is never visually buried under other dots.
  const dominated = plotted.filter((c) => !c.is_pareto_optimal);
  const pareto = plotted.filter((c) => c.is_pareto_optimal && !c.is_selected);
  const winner = plotted.find((c) => c.is_selected);

  return (
    <figure className="chart-figure">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Scatter plot of print time versus material usage for every tested configuration, with Pareto-optimal and selected candidates highlighted"
        className="pareto-svg"
      >
        <defs>
          <radialGradient id={gradientId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--chart-winner)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--chart-winner)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* gridlines */}
        {yTicks.map((t) => (
          <line key={`gy-${t}`} x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(t)} y2={y(t)} className="chart-gridline" />
        ))}
        {xTicks.map((t) => (
          <line key={`gx-${t}`} x1={x(t)} x2={x(t)} y1={MARGIN.top} y2={MARGIN.top + PLOT_H} className="chart-gridline" />
        ))}

        {/* axes */}
        <line x1={MARGIN.left} x2={MARGIN.left} y1={MARGIN.top} y2={MARGIN.top + PLOT_H} className="chart-axis" />
        <line
          x1={MARGIN.left}
          x2={WIDTH - MARGIN.right}
          y1={MARGIN.top + PLOT_H}
          y2={MARGIN.top + PLOT_H}
          className="chart-axis"
        />

        {/* tick labels */}
        {yTicks.map((t) => (
          <text key={`yl-${t}`} x={MARGIN.left - 10} y={y(t)} className="chart-tick-label" textAnchor="end" dominantBaseline="middle">
            {t}g
          </text>
        ))}
        {xTicks.map((t) => (
          <text key={`xl-${t}`} x={x(t)} y={MARGIN.top + PLOT_H + 20} className="chart-tick-label" textAnchor="middle">
            {formatDuration(t)}
          </text>
        ))}

        {/* axis titles */}
        <text x={MARGIN.left + PLOT_W / 2} y={HEIGHT - 6} textAnchor="middle" className="chart-axis-title">
          Print time
        </text>
        <text
          x={-(MARGIN.top + PLOT_H / 2)}
          y={16}
          textAnchor="middle"
          transform="rotate(-90)"
          className="chart-axis-title"
        >
          Material usage
        </text>

        {winner && <circle cx={x(winner.print_time_seconds!)} cy={y(winner.filament_grams!)} r={26} fill={`url(#${gradientId})`} />}

        {dominated.map((c) => (
          <circle key={c.id} cx={x(c.print_time_seconds!)} cy={y(c.filament_grams!)} r={5} className="chart-dot chart-dot-tested">
            <title>{`${candidateLabel(c)} — ${formatDuration(c.print_time_seconds!)}, ${formatGrams(c.filament_grams!)}`}</title>
          </circle>
        ))}
        {pareto.map((c) => (
          <circle key={c.id} cx={x(c.print_time_seconds!)} cy={y(c.filament_grams!)} r={6} className="chart-dot chart-dot-pareto">
            <title>{`${candidateLabel(c)} — ${formatDuration(c.print_time_seconds!)}, ${formatGrams(c.filament_grams!)} (Pareto-optimal)`}</title>
          </circle>
        ))}
        {winner && (
          <g>
            <circle cx={x(winner.print_time_seconds!)} cy={y(winner.filament_grams!)} r={8} className="chart-dot chart-dot-winner">
              <title>{`${candidateLabel(winner)} — ${formatDuration(winner.print_time_seconds!)}, ${formatGrams(winner.filament_grams!)} (Selected)`}</title>
            </circle>
            <text
              x={x(winner.print_time_seconds!) + 12}
              y={y(winner.filament_grams!) - 10}
              className="chart-winner-label"
            >
              Selected
            </text>
          </g>
        )}
      </svg>

      <figcaption className="chart-legend">
        <span className="legend-item">
          <span className="legend-dot legend-dot-tested" /> Tested
        </span>
        <span className="legend-item">
          <span className="legend-dot legend-dot-pareto" /> Pareto-optimal
        </span>
        {winner && (
          <span className="legend-item">
            <span className="legend-dot legend-dot-winner" /> Selected
          </span>
        )}
      </figcaption>
    </figure>
  );
}
