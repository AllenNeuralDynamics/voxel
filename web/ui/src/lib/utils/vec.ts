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

/** Parse a Vec3D from "z,y,x" string, [z,y,x] array, or {z,y,x} object. Returns null on malformed input. */
export function parseVec3D(val: unknown): Vec3D | null {
  if (typeof val === 'string') {
    const parts = val.split(',').map(Number);
    if (parts.length === 3 && parts.every(Number.isFinite)) {
      return { z: parts[0], y: parts[1], x: parts[2] };
    }
  }
  if (Array.isArray(val) && val.length === 3) {
    return { z: Number(val[0]), y: Number(val[1]), x: Number(val[2]) };
  }
  if (val && typeof val === 'object' && 'z' in val && 'y' in val && 'x' in val) {
    return { z: Number((val as Vec3D).z), y: Number((val as Vec3D).y), x: Number((val as Vec3D).x) };
  }
  return null;
}
