/** 2D vector with y, x components (matches backend Vec2D/IVec2D). */
export interface Vec2D {
  y: number;
  x: number;
}

/** 3D vector with z, y, x components (matches backend Vec3D/IVec3D). */
export interface Vec3D {
  z: number;
  y: number;
  x: number;
}

/** Parse a Vec2D from its saved form, a {x, y} map. Returns null on malformed input. */
export function parseVec2D(val: unknown): Vec2D | null {
  if (val && typeof val === 'object' && 'y' in val && 'x' in val) {
    const { y, x } = val as Vec2D;
    if (Number.isFinite(y) && Number.isFinite(x)) return { y, x };
  }
  return null;
}

export function clampTopLeft(value: number, viewSize: number): number {
  return Math.max(0, Math.min(value, 1 - viewSize));
}
