import type { AcquisitionTask, FootprintBounds, Point2D } from './types';

export interface RegionBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Return the conservative FOV used to space positions for the selected profiles. */
export function planningFov(
  profileFovs: Readonly<Record<string, Readonly<Record<string, FootprintBounds>>>>,
  profiles: readonly string[]
): [width: number, height: number] | null {
  const bounds = profiles.flatMap((profile) => Object.values(profileFovs[profile] ?? {}));
  const width = Math.min(...bounds.map((bound) => bound.max_x - bound.min_x));
  const height = Math.min(...bounds.map((bound) => bound.max_y - bound.min_y));
  return Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0 ? [width, height] : null;
}

/** Place the first grid center so the minimum tile count covers the region with balanced overhang. */
export function defaultGridAnchor(
  region: RegionBounds,
  [width, height]: readonly [number, number],
  overlap: number
): Point2D {
  return {
    x: axisAnchor(region.minX, region.maxX, width, overlap),
    y: axisAnchor(region.minY, region.maxY, height, overlap)
  };
}

export function rectanglePoints(region: RegionBounds): Point2D[] {
  return [
    { x: region.minX, y: region.minY },
    { x: region.maxX, y: region.minY },
    { x: region.maxX, y: region.maxY },
    { x: region.minX, y: region.maxY }
  ];
}

/** Create a task that acquires the supplied positions in their given order. */
export function createPositionTask(
  points: readonly Point2D[],
  profile: string,
  z: { start: number; end: number }
): AcquisitionTask {
  return {
    id: crypto.randomUUID().replaceAll('-', ''),
    layout: { type: 'positions', points: points.map((point) => ({ ...point })) },
    profiles: [profile],
    z: { type: 'fixed', ...z },
    traversal: 'custom',
    volume_order: 'position_major'
  };
}

/** Create a rectangular area task using the compact default grid alignment. */
export function createAreaTask(
  region: RegionBounds,
  fov: readonly [number, number],
  overlap: number,
  profile: string,
  z: { start: number; end: number }
): AcquisitionTask {
  return {
    id: crypto.randomUUID().replaceAll('-', ''),
    layout: {
      type: 'area',
      points: rectanglePoints(region),
      grid: { anchor: defaultGridAnchor(region, fov, overlap), overlap }
    },
    profiles: [profile],
    z: { type: 'fixed', ...z },
    traversal: 'snake_row',
    volume_order: 'position_major'
  };
}

function axisAnchor(min: number, max: number, size: number, overlap: number): number {
  const pitch = size * (1 - overlap);
  const count = Math.max(1, Math.ceil((max - min - size) / pitch) + 1);
  const overhang = size + (count - 1) * pitch - (max - min);
  return min + size / 2 - overhang / 2;
}
