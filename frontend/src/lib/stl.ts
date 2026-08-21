/**
 * Client-side STL parsing helpers. Everything here derives only from the
 * geometry itself — dimensions, triangle count. No print time, material,
 * printability, or manufacturing property is ever estimated here; those
 * stay real PrusaSlicer output from the actual backend pipeline (see
 * docs/architecture.md).
 */

import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

/** Hard ceiling before we even attempt to parse — STLLoader.parse() is
 * synchronous and can freeze the tab on a pathologically large file.
 * 30MB comfortably covers real prototyping-scale parts while refusing to
 * even try on something absurd. */
export const MAX_STL_BYTES = 30 * 1024 * 1024;

export interface ParsedStl {
  geometry: THREE.BufferGeometry;
  triangleCount: number;
  dimensions: { x: number; y: number; z: number };
}

export class StlTooLargeError extends Error {}
export class StlParseError extends Error {}
export class StlEmptyGeometryError extends Error {}

export function readFileAsArrayBuffer(file: File): Promise<ArrayBuffer> {
  return file.arrayBuffer();
}

/**
 * Parse raw STL bytes into geometry + truthfully-derived stats. Throws one
 * of the typed errors above on anything that isn't a valid, non-empty mesh
 * — callers render a clean error state, never a crash.
 */
export function parseStl(bytes: ArrayBuffer): ParsedStl {
  if (bytes.byteLength === 0) {
    throw new StlEmptyGeometryError("The file is empty.");
  }
  if (bytes.byteLength > MAX_STL_BYTES) {
    throw new StlTooLargeError(
      `File is ${(bytes.byteLength / (1024 * 1024)).toFixed(1)}MB, over the ${MAX_STL_BYTES / (1024 * 1024)}MB preview limit.`,
    );
  }

  let geometry: THREE.BufferGeometry;
  try {
    geometry = new STLLoader().parse(bytes);
  } catch {
    // STLLoader's own error text is low-level parser internals (e.g. "Offset
    // is outside the bounds of the DataView") — accurate but not
    // meaningful to a user; a bad/non-STL file just isn't previewable.
    throw new StlParseError("This doesn't appear to be a valid STL file.");
  }

  const positionAttr = geometry.getAttribute("position");
  if (!positionAttr || positionAttr.count === 0) {
    throw new StlEmptyGeometryError("The STL contains no geometry.");
  }

  geometry.computeBoundingBox();
  geometry.computeVertexNormals();

  const box = geometry.boundingBox!;
  const size = new THREE.Vector3();
  box.getSize(size);

  if (!Number.isFinite(size.x) || !Number.isFinite(size.y) || !Number.isFinite(size.z) || size.length() === 0) {
    throw new StlEmptyGeometryError("The STL's geometry has no measurable extent.");
  }

  return {
    geometry,
    triangleCount: positionAttr.count / 3,
    dimensions: { x: size.x, y: size.y, z: size.z },
  };
}

export function formatMm(value: number): string {
  return `${value.toFixed(1)}mm`;
}

export function formatTriangleCount(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}k` : String(Math.round(count));
}
