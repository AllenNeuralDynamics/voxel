export interface Point {
  x: number;
  y: number;
}

/** In µm, on the map's 2 axes. */
export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** The world point at the middle of the canvas, and pixels per µm. */
export interface Viewport {
  cx: number;
  cy: number;
  scale: number;
}

/** Where world 0 sits on the canvas, in pixels, and pixels per µm. */
export interface ViewTransform {
  x: number;
  y: number;
  scale: number;
}

/** The map's math: world µm with the second axis up, and canvas pixels with y down. */
export class Geometry {
  /** For a group under the translated stage: world µm to pixels. */
  static world(scale: number): { scaleX: number; scaleY: number } {
    return { scaleX: scale, scaleY: -scale };
  }

  /** For a group under the translated stage: plain canvas pixels. */
  static screen(view: ViewTransform): { x: number; y: number } {
    return { x: -view.x, y: -view.y };
  }

  static project(point: Point, view: ViewTransform): Point {
    return { x: view.x + point.x * view.scale, y: view.y - point.y * view.scale };
  }

  static unproject(point: Point, view: ViewTransform): Point {
    return { x: (point.x - view.x) / view.scale, y: (view.y - point.y) / view.scale };
  }

  static box(a: Point, b: Point): Bounds {
    return { minX: Math.min(a.x, b.x), minY: Math.min(a.y, b.y), maxX: Math.max(a.x, b.x), maxY: Math.max(a.y, b.y) };
  }

  static around(points: Point[]): Bounds | null {
    if (points.length === 0) return null;
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
  }

  static union(all: Bounds[]): Bounds | null {
    if (all.length === 0) return null;
    return {
      minX: Math.min(...all.map((b) => b.minX)),
      minY: Math.min(...all.map((b) => b.minY)),
      maxX: Math.max(...all.map((b) => b.maxX)),
      maxY: Math.max(...all.map((b) => b.maxY))
    };
  }

  static intersect(a: Bounds, b: Bounds): Bounds | null {
    const result = {
      minX: Math.max(a.minX, b.minX),
      minY: Math.max(a.minY, b.minY),
      maxX: Math.min(a.maxX, b.maxX),
      maxY: Math.min(a.maxY, b.maxY)
    };
    return result.maxX >= result.minX && result.maxY >= result.minY ? result : null;
  }

  static contains(bounds: Bounds, point: Point): boolean {
    return point.x >= bounds.minX && point.x <= bounds.maxX && point.y >= bounds.minY && point.y <= bounds.maxY;
  }

  static screenRect(bounds: Bounds, view: ViewTransform): { x: number; y: number; width: number; height: number } {
    const a = Geometry.project({ x: bounds.minX, y: bounds.minY }, view);
    const b = Geometry.project({ x: bounds.maxX, y: bounds.maxY }, view);
    return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
  }

  /** Fills 90 % of the canvas, padded by `pad` µm on each side. */
  static fit(bounds: Bounds, width: number, height: number, maxScale: number, pad = 0): Viewport {
    const w = Math.max(bounds.maxX - bounds.minX + 2 * pad, 1e-3);
    const h = Math.max(bounds.maxY - bounds.minY + 2 * pad, 1e-3);
    return {
      cx: (bounds.minX + bounds.maxX) / 2,
      cy: (bounds.minY + bounds.maxY) / 2,
      scale: Math.min(maxScale, 0.9 * Math.min(width / w, height / h))
    };
  }

  /** The convex hull, counterclockwise (Andrew's monotone chain). */
  static hull(points: Point[]): Point[] {
    const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
    if (sorted.length < 3) return sorted;
    const cross = (o: Point, a: Point, b: Point) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    const lower: Point[] = [];
    for (const point of sorted) {
      while (lower.length >= 2 && cross(lower.at(-2)!, lower.at(-1)!, point) <= 0) lower.pop();
      lower.push(point);
    }
    const upper: Point[] = [];
    for (const point of sorted.toReversed()) {
      while (upper.length >= 2 && cross(upper.at(-2)!, upper.at(-1)!, point) <= 0) upper.pop();
      upper.push(point);
    }
    return [...lower.slice(0, -1), ...upper.slice(0, -1)];
  }
}
