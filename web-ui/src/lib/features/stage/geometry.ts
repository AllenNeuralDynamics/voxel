export interface Point {
  x: number;
  y: number;
}

/** Physical coordinates in micrometers. */
export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Orientation {
  x: 1 | -1;
  y: 1 | -1;
}

export interface Viewport {
  cx: number;
  cy: number;
  scale: number;
}

/** Screen translation and scale derived from a viewport and canvas dimensions. */
export interface ViewTransform {
  x: number;
  y: number;
  scale: number;
}

/** Add world scaling beneath the translated Stage, with no transformed ancestors in between. */
export function worldTransform(scale: number, orientation: Orientation) {
  return { scaleX: scale * orientation.x, scaleY: -scale * orientation.y };
}

/** Cancel Stage translation for pixel coordinates, with no transformed ancestors in between. */
export function screenTransform(view: ViewTransform) {
  return { x: -view.x, y: -view.y };
}

export function project(point: Point, view: ViewTransform, orientation: Orientation): Point {
  return {
    x: view.x + point.x * view.scale * orientation.x,
    y: view.y - point.y * view.scale * orientation.y
  };
}

export function unproject(point: Point, view: ViewTransform, orientation: Orientation): Point {
  return {
    x: (point.x - view.x) / (view.scale * orientation.x),
    y: (view.y - point.y) / (view.scale * orientation.y)
  };
}

export function box(a: Point, b: Point): Bounds {
  return { minX: Math.min(a.x, b.x), minY: Math.min(a.y, b.y), maxX: Math.max(a.x, b.x), maxY: Math.max(a.y, b.y) };
}

export function screenRect(bounds: Bounds, view: ViewTransform, orientation: Orientation) {
  const a = project({ x: bounds.minX, y: bounds.minY }, view, orientation);
  const b = project({ x: bounds.maxX, y: bounds.maxY }, view, orientation);
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
}

export function intersect(a: Bounds, b: Bounds): Bounds | null {
  const result = {
    minX: Math.max(a.minX, b.minX),
    minY: Math.max(a.minY, b.minY),
    maxX: Math.min(a.maxX, b.maxX),
    maxY: Math.min(a.maxY, b.maxY)
  };
  return result.maxX > result.minX && result.maxY > result.minY ? result : null;
}

export function fit(bounds: Bounds, width: number, height: number, maxScale: number): Viewport {
  const scale = Math.min(
    maxScale,
    0.9 * Math.min(width / (bounds.maxX - bounds.minX), height / (bounds.maxY - bounds.minY))
  );
  return {
    cx: (bounds.minX + bounds.maxX) / 2,
    cy: (bounds.minY + bounds.maxY) / 2,
    scale
  };
}
