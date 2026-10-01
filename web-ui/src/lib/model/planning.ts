import type { AcquisitionTask, Bounds, Point2D, XYDefinition } from './types';

export interface RegionBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Return the conservative FOV used to space positions for the selected profiles. */
export function planningFov(
  profileFovs: Readonly<Record<string, Readonly<Record<string, Bounds>>>>,
  profiles: readonly string[]
): [width: number, height: number] | null {
  const bounds = profiles.flatMap((profile) => Object.values(profileFovs[profile] ?? {}));
  const width = Math.min(...bounds.map((bound) => bound.max.x - bound.min.x));
  const height = Math.min(...bounds.map((bound) => bound.max.y - bound.min.y));
  return Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0 ? [width, height] : null;
}

export function pointBounds(points: readonly Point2D[]): RegionBounds {
  return {
    minX: Math.min(...points.map(({ x }) => x)),
    minY: Math.min(...points.map(({ y }) => y)),
    maxX: Math.max(...points.map(({ x }) => x)),
    maxY: Math.max(...points.map(({ y }) => y))
  };
}

/** Return the ordered outer boundary derived from an XY definition. */
export function xyBoundary(xy: XYDefinition): Point2D[] {
  return xy.mode === 'bounding_box' ? rectanglePoints(pointBounds(xy.points)) : convexHull(xy.points);
}

export function convexHull(points: readonly Point2D[]): Point2D[] {
  const ordered = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (origin: Point2D, first: Point2D, second: Point2D) =>
    (first.x - origin.x) * (second.y - origin.y) - (first.y - origin.y) * (second.x - origin.x);
  const half = (input: readonly Point2D[]) => {
    const result: Point2D[] = [];
    for (const point of input) {
      while (result.length >= 2 && cross(result.at(-2)!, result.at(-1)!, point) <= 0) result.pop();
      result.push(point);
    }
    return result;
  };
  return [...half(ordered).slice(0, -1), ...half(ordered.toReversed()).slice(0, -1)];
}

export function rectanglePoints(region: RegionBounds): Point2D[] {
  return [
    { x: region.minX, y: region.minY },
    { x: region.maxX, y: region.minY },
    { x: region.maxX, y: region.maxY },
    { x: region.minX, y: region.maxY }
  ];
}

/** Remap points proportionally from their current bounds into new bounds. */
export function resizePointsToBounds(points: readonly Point2D[], bounds: RegionBounds): Point2D[] {
  const current = pointBounds(points);
  const width = current.maxX - current.minX;
  const height = current.maxY - current.minY;
  return points.map(({ x, y }) => ({
    x: bounds.minX + ((x - current.minX) / width) * (bounds.maxX - bounds.minX),
    y: bounds.minY + ((y - current.minY) / height) * (bounds.maxY - bounds.minY)
  }));
}

/** Recover axis-aligned bounds when four points describe exactly one rectangle. */
export function rectangularBounds(points: readonly Point2D[]): RegionBounds | null {
  if (points.length !== 4) return null;
  const xs = [...new Set(points.map(({ x }) => x))].sort((a, b) => a - b);
  const ys = [...new Set(points.map(({ y }) => y))].sort((a, b) => a - b);
  if (xs.length !== 2 || ys.length !== 2 || xs[0] === xs[1] || ys[0] === ys[1]) return null;
  const corners = new Set(points.map(({ x, y }) => `${x}\0${y}`));
  if (xs.some((x) => ys.some((y) => !corners.has(`${x}\0${y}`)))) return null;
  return { minX: xs[0], minY: ys[0], maxX: xs[1], maxY: ys[1] };
}

/** Create a task that acquires the supplied positions in their given order. */
export function createPositionTask(
  points: readonly Point2D[],
  profile: string,
  z: { start: number; end: number }
): AcquisitionTask {
  return {
    id: crypto.randomUUID().replaceAll('-', ''),
    xy: {
      mode: 'explicit_points',
      points: points.map((point) => ({ ...point })),
      overlap: { x: 0.1, y: 0.1 }
    },
    profiles: [profile],
    z: { type: 'fixed', ...z },
    traversal: 'custom',
    iteration: 'position_major'
  };
}

/** Create a rectangular area task using the compact default grid alignment. */
export function createAreaTask(
  region: RegionBounds,
  overlap: Point2D,
  profile: string,
  z: { start: number; end: number }
): AcquisitionTask {
  return {
    id: crypto.randomUUID().replaceAll('-', ''),
    xy: {
      mode: 'bounding_box',
      points: rectanglePoints(region),
      overlap
    },
    profiles: [profile],
    z: { type: 'fixed', ...z },
    traversal: 'snake_row',
    iteration: 'position_major'
  };
}
