import type { StlSource } from "./StlViewer";
import { LazyStlViewer } from "./LazyStlViewer";

/** The "Your Part" card — wraps StlViewer with consistent chrome across the
 * setup screen, the working/replay views, and the final result. `compact`
 * shrinks it for the side-by-side placements where it shouldn't compete
 * with the main content. */
export function PartPreviewPanel({ source, compact = false }: { source: StlSource | null; compact?: boolean }) {
  if (!source) return null;

  return (
    <section className={`result-card part-preview-card ${compact ? "part-preview-card-compact" : ""}`}>
      <h2>Your part</h2>
      <LazyStlViewer source={source} compact={compact} />
    </section>
  );
}
