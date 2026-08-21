import { lazy, Suspense } from "react";
import type { StlSource } from "./StlViewer";

// Three.js is a real dependency (~200KB gzipped) that most page loads never
// need (idle screen, error states without a model, etc.) — code-split it so
// it's only fetched once a model actually needs rendering.
const StlViewer = lazy(() => import("./StlViewer").then((m) => ({ default: m.StlViewer })));

export function LazyStlViewer({ source, compact }: { source: StlSource; compact?: boolean }) {
  return (
    <Suspense
      fallback={
        <div className={`stl-viewer-canvas-host ${compact ? "stl-viewer-canvas-host-compact" : ""}`}>
          <div className="stl-viewer-overlay">Loading viewer...</div>
        </div>
      }
    >
      <StlViewer source={source} compact={compact} />
    </Suspense>
  );
}
