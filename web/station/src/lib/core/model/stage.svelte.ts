/** The stage of the open instrument: its axes, imageable bounds and moves. */
import { AxisHandle } from './device.svelte';
import type { StageOrientation } from './types';

export type StageAxis = 'x' | 'y' | 'z';

/** Stage extent per axis (µm). Structurally a superset of the renderer's 2D `Bounds` (X/Y). */
export interface StageBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

/** Axis is treated as "arrived" once it's within this many µm of the commanded target. */
const TARGET_TOLERANCE_UM = 0.5;

/**
 * A value object over the mapped stage axes (resolved handles) + FOV + orientation: derived geometry
 * (imageable bounds, normalized position) and whole-stage move/halt commands. Constructed reactively by
 * the instrument (re-made when the mapping or FOV changes); the handles carry their own live position.
 */
export class Stage {
  readonly #getFov: () => [number, number] | null;

  /** Last commanded absolute position (µm), from any in-app surface. Null until something moves. */
  target = $state.raw<{ x?: number; y?: number; z?: number } | null>(null);

  constructor(
    readonly x: AxisHandle,
    readonly y: AxisHandle,
    readonly z: AxisHandle,
    getFov: () => [number, number] | null,
    /** Per-axis display sign shared with the renderers (hardcoded upstream for now). */
    readonly orientation: StageOrientation
  ) {
    this.#getFov = getFov;
  }

  /** Field of view (µm), read live so a FOV change doesn't rebuild the whole Stage. */
  get fov(): [number, number] | null {
    return this.#getFov();
  }

  axis(a: StageAxis): AxisHandle {
    return a === 'x' ? this.x : a === 'y' ? this.y : this.z;
  }

  position(a: StageAxis): number {
    return this.axis(a).position?.value ?? 0;
  }
  moving(a: StageAxis): boolean {
    return this.axis(a).isMoving?.value === true;
  }

  get anyMoving(): boolean {
    return this.moving('x') || this.moving('y') || this.moving('z');
  }

  /** True while the stage is still short of its commanded target on any axis. */
  readonly targetPending: boolean = $derived.by(() => {
    const t = this.target;
    if (!t) return false;
    return (['x', 'y', 'z'] as const).some((a) => {
      const want = t[a];
      return want != null && Math.abs(this.position(a) - want) > TARGET_TOLERANCE_UM;
    });
  });

  /** Raw [lower, upper] soft limits for an axis (µm), defaulting to [0, 1] until the limits stream in. */
  #range(a: StageAxis): [number, number] {
    const h = this.axis(a);
    return [h.lowerLimit?.value ?? 0, h.upperLimit?.value ?? 1];
  }

  /** Normalize an absolute µm value onto [0,1] for an axis (guards a zero-length range). */
  normOf(a: StageAxis, um: number): number {
    const [lo, hi] = this.#range(a);
    return hi > lo ? (um - lo) / (hi - lo) : 0;
  }

  /** Normalized [0,1] position along an axis. */
  norm(a: StageAxis): number {
    return this.normOf(a, this.position(a));
  }
  denorm(a: StageAxis, n: number): number {
    const [lo, hi] = this.#range(a);
    return lo + Math.min(1, Math.max(0, n)) * (hi - lo);
  }

  /**
   * Stage extent per axis (µm). `includeFov` expands X/Y by half a FOV on each side (the imageable
   * extent, for the top-down view); Z is unaffected. Null until the X/Y soft limits are known.
   */
  bounds(includeFov = false): StageBounds | null {
    const xl = this.x.lowerLimit?.value;
    const xu = this.x.upperLimit?.value;
    const yl = this.y.lowerLimit?.value;
    const yu = this.y.upperLimit?.value;
    if (xl == null || xu == null || yl == null || yu == null) return null;
    const [fw, fh] = includeFov ? (this.fov ?? [0, 0]) : [0, 0];
    const [zl, zu] = this.#range('z');
    return { minX: xl - fw / 2, maxX: xu + fw / 2, minY: yl - fh / 2, maxY: yu + fh / 2, minZ: zl, maxZ: zu };
  }

  /** Drive the stage to an absolute position (µm); axes omitted from `pos` are left unchanged. */
  moveTo(pos: { x?: number; y?: number; z?: number }): Promise<unknown> {
    this.target = { ...this.target, ...pos };
    const moves: Promise<unknown>[] = [];
    if (pos.x != null) moves.push(this.x.move(pos.x));
    if (pos.y != null) moves.push(this.y.move(pos.y));
    if (pos.z != null) moves.push(this.z.move(pos.z));
    return Promise.all(moves);
  }

  /** Halt all stage axes, abandoning any commanded target. */
  halt(): Promise<unknown> {
    this.target = null;
    return Promise.all([this.x.halt(), this.y.halt(), this.z.halt()]);
  }
}
