import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  formatMm,
  formatTriangleCount,
  parseStl,
  readFileAsArrayBuffer,
  StlEmptyGeometryError,
  StlParseError,
  StlTooLargeError,
  type ParsedStl,
} from "../lib/stl";

export type StlSource = { kind: "file"; file: File } | { kind: "url"; url: string };

type ViewerStatus = { kind: "loading" } | { kind: "ready"; stats: ParsedStl["dimensions"] & { triangleCount: number } } | { kind: "error"; message: string };

const AUTO_ROTATE_RESUME_MS = 1500;
const FIT_PADDING = 1.6;

/** Same `source` identity (file reference, or url string) is treated as
 * "already showing this" — avoids re-parsing/re-building the scene on
 * every unrelated re-render of a parent. */
function sourceKey(source: StlSource): string {
  return source.kind === "file" ? `file:${source.file.name}:${source.file.size}:${source.file.lastModified}` : `url:${source.url}`;
}

/**
 * Self-contained Three.js STL viewer: parses locally (File.arrayBuffer() or
 * a same-origin static asset fetch — never uploads anywhere), frames the
 * camera to the model's real bounding box, and cleans up every GPU
 * resource on unmount/source change. No print time, material, or
 * manufacturing property is computed here — see lib/stl.ts.
 */
export function StlViewer({ source, compact = false }: { source: StlSource; compact?: boolean }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<ViewerStatus>({ kind: "loading" });
  const resetViewRef = useRef<() => void>(() => {});

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    const abortController = new AbortController();
    setStatus({ kind: "loading" });

    let renderer: THREE.WebGLRenderer | null = null;
    let controls: OrbitControls | null = null;
    let geometry: THREE.BufferGeometry | null = null;
    let material: THREE.Material | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let frameId = 0;
    let resumeTimer: ReturnType<typeof setTimeout> | null = null;

    async function load() {
      try {
        const bytes =
          source.kind === "file"
            ? await readFileAsArrayBuffer(source.file)
            : await fetch(source.url, { signal: abortController.signal }).then((r) => {
                if (!r.ok) throw new StlParseError(`Could not load model (HTTP ${r.status}).`);
                return r.arrayBuffer();
              });
        if (cancelled) return;

        const parsed = parseStl(bytes);
        if (cancelled) return;
        buildScene(parsed);
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof StlTooLargeError || err instanceof StlParseError || err instanceof StlEmptyGeometryError
            ? err.message
            : "Could not preview this file as STL.";
        setStatus({ kind: "error", message });
      }
    }

    function buildScene(parsed: ParsedStl) {
      if (!container) return;
      geometry = parsed.geometry;
      geometry.center();

      const scene = new THREE.Scene();

      const width = container.clientWidth || 1;
      const height = container.clientHeight || 1;
      const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
      camera.up.set(0, 0, 1); // STL/print-bed convention: Z is up

      try {
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      } catch {
        setStatus({ kind: "error", message: "3D preview isn't available in this browser." });
        return;
      }
      if (!renderer.getContext()) {
        setStatus({ kind: "error", message: "3D preview isn't available in this browser." });
        return;
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(width, height, false);
      while (container.firstChild) container.firstChild.remove();
      container.appendChild(renderer.domElement);

      material = new THREE.MeshStandardMaterial({ color: 0xd9d4c6, roughness: 0.65, metalness: 0.05 });
      const mesh = new THREE.Mesh(geometry, material);
      scene.add(mesh);

      scene.add(new THREE.AmbientLight(0xffffff, 0.55));
      const key = new THREE.DirectionalLight(0xffffff, 1.1);
      key.position.set(1, -1, 2);
      scene.add(key);
      const fill = new THREE.DirectionalLight(0xffffff, 0.4);
      fill.position.set(-1, 1, 0.5);
      scene.add(fill);

      const { x, y, z } = parsed.dimensions;
      const maxDim = Math.max(x, y, z, 0.001);
      const grid = new THREE.GridHelper(maxDim * 3, 12, 0x999588, 0xd8d3c5);
      grid.rotation.x = Math.PI / 2; // GridHelper defaults to the XZ plane; STL convention is XY
      grid.position.z = -z / 2;
      scene.add(grid);

      const fovRad = (camera.fov * Math.PI) / 180;
      const fitDistance = (maxDim / (2 * Math.tan(fovRad / 2))) * FIT_PADDING;
      const dir = new THREE.Vector3(1, -1, 0.6).normalize();
      const initialPosition = dir.clone().multiplyScalar(fitDistance);
      camera.position.copy(initialPosition);
      camera.lookAt(0, 0, 0);

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.target.set(0, 0, 0);
      controls.minDistance = fitDistance * 0.15;
      controls.maxDistance = fitDistance * 4;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 1.6;

      controls.addEventListener("start", () => {
        if (resumeTimer) clearTimeout(resumeTimer);
        if (controls) controls.autoRotate = false;
      });
      controls.addEventListener("end", () => {
        if (resumeTimer) clearTimeout(resumeTimer);
        resumeTimer = setTimeout(() => {
          if (controls) controls.autoRotate = true;
        }, AUTO_ROTATE_RESUME_MS);
      });

      resetViewRef.current = () => {
        if (!controls) return;
        camera.position.copy(initialPosition);
        controls.target.set(0, 0, 0);
        controls.update();
      };

      resizeObserver = new ResizeObserver(() => {
        if (!container || !renderer) return;
        const w = container.clientWidth || 1;
        const h = container.clientHeight || 1;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      });
      resizeObserver.observe(container);

      function animate() {
        frameId = requestAnimationFrame(animate);
        controls?.update();
        if (renderer) renderer.render(scene, camera);
      }
      animate();

      setStatus({ kind: "ready", stats: { x, y, z, triangleCount: parsed.triangleCount } });
    }

    load();

    return () => {
      cancelled = true;
      abortController.abort();
      if (frameId) cancelAnimationFrame(frameId);
      if (resumeTimer) clearTimeout(resumeTimer);
      resizeObserver?.disconnect();
      controls?.dispose();
      geometry?.dispose();
      material?.dispose();
      if (renderer) {
        renderer.dispose();
        renderer.domElement.remove();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey(source)]);

  return (
    <div className={`stl-viewer ${compact ? "stl-viewer-compact" : ""}`}>
      <div className="stl-viewer-canvas-host">
        {/* This inner div is imperatively owned by the Three.js effect below
            (canvas append/remove) — React never renders children into it.
            The overlay is a separate sibling React fully owns instead, so
            the two never fight over the same node's children (that
            conflict threw a real removeChild crash before this split). */}
        <div ref={containerRef} className="stl-viewer-canvas-inner" />
        {status.kind === "loading" && <div className="stl-viewer-overlay">Loading model…</div>}
        {status.kind === "error" && <div className="stl-viewer-overlay stl-viewer-overlay-error">{status.message}</div>}
      </div>
      {status.kind === "ready" && (
        <div className="stl-viewer-footer">
          <span className="stl-viewer-stats">
            {formatMm(status.stats.x)} × {formatMm(status.stats.y)} × {formatMm(status.stats.z)}
            {!compact && <> · {formatTriangleCount(status.stats.triangleCount)} triangles</>}
          </span>
          <button type="button" className="stl-viewer-reset" onClick={() => resetViewRef.current()}>
            Reset view
          </button>
        </div>
      )}
    </div>
  );
}
