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

/** Parse a Vec2D from "y,x" string, [y,x] array, or {y,x} object. Returns null on malformed input. */
export function parseVec2D(val: unknown): Vec2D | null {
  if (typeof val === 'string') {
    const parts = val.split(',').map(Number);
    if (parts.length === 2 && parts.every(Number.isFinite)) {
      return { y: parts[0], x: parts[1] };
    }
  }
  if (Array.isArray(val) && val.length === 2) {
    return { y: Number(val[0]), x: Number(val[1]) };
  }
  if (val && typeof val === 'object' && 'y' in val && 'x' in val) {
    return { y: Number((val as Vec2D).y), x: Number((val as Vec2D).x) };
  }
  return null;
}

export function clampTopLeft(value: number, viewSize: number): number {
  return Math.max(0, Math.min(value, 1 - viewSize));
}
