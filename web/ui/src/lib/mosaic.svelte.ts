/**
 * MosaicManager — tile layout (grid config + camera FOV + derived tiles) and
 * alignment helpers.
 *
 * A mosaic is the 2D XY arrangement of tiles the acquisition will visit.
 * Each tile is one camera field-of-view wide, stepped by (1 - overlap) × FOV.
 *
 * Self-subscribes to the ``status`` WS topic for live grid + fov updates;
 * takes ``client`` for REST + a ``getStage`` closure for tile bounds.
 */

import { toast } from 'svelte-sonner';
import type { MsgClient } from '$lib/wire.svelte';
import type { Stage } from '$lib/microscope';
import { SnapshotStore } from '$lib/preview/snapshots.svelte';
import type { GridConfig } from '$lib/protocol/stacks';
import type { Tile } from './grid/types';
import type { SessionStateUpdate } from '$lib/protocol';

/** Edge to align the mosaic to relative to the current FOV position. */
export type AlignEdge = 'top' | 'bottom' | 'left' | 'right' | 'center';

const DEFAULT_GRID: GridConfig = { x_offset: 0, y_offset: 0, overlap_x: 0.1, overlap_y: 0.1 };
const DEFAULT_FOV = { width: 5000, height: 5000 };

export class MosaicManager {
  /** Thumbnail size (pixels, square) for snapshot previews. */
  static readonly SNAPSHOT_THUMB_SIZE = 256;

  config = $state<GridConfig>(DEFAULT_GRID);
  fov = $state<{ width: number; height: number }>(DEFAULT_FOV);
  readonly snaps = new SnapshotStore();

  readonly #client: MsgClient;
  readonly #getStage: () => Stage | null;
  readonly #unsubscribe: () => void;

  constructor(client: MsgClient, getStage: () => Stage | null, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.#getStage = getStage;
    this.handleStatus(initialStatus);
    this.#unsubscribe = client.on('app.status', (status) => {
      this.handleStatus(status.session ?? null);
    });
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.config = s?.grid ?? DEFAULT_GRID;
    this.fov = s?.fov ? { width: s.fov[0], height: s.fov[1] } : DEFAULT_FOV;
  }

  dispose(): void {
    this.#unsubscribe();
  }

  // ── Derived ──────────────────────────────────────────────

  offsetX = $derived<number>(this.config.x_offset);
  offsetY = $derived<number>(this.config.y_offset);
  spacingX = $derived<number>(this.fov.width * (1 - this.config.overlap_x));
  spacingY = $derived<number>(this.fov.height * (1 - this.config.overlap_y));

  list = $derived.by<Tile[]>(() => {
    const gc = this.config;
    const fov = this.fov;
    const stage = this.#getStage();
    const sx = stage?.x;
    const sy = stage?.y;
    if (!sx || !sy) return [];

    const stepW = fov.width * (1 - gc.overlap_x);
    const stepH = fov.height * (1 - gc.overlap_y);
    if (stepW <= 0 || stepH <= 0) return [];

    const stageW = sx.range;
    const stageH = sy.range;

    const colMin = Math.ceil(-gc.x_offset / stepW);
    const colMax = Math.floor((stageW - gc.x_offset) / stepW) + 1;
    const rowMin = Math.ceil(-gc.y_offset / stepH);
    const rowMax = Math.floor((stageH - gc.y_offset) / stepH) + 1;

    const tiles: Tile[] = [];
    for (let row = rowMin; row < rowMax; row++) {
      for (let col = colMin; col < colMax; col++) {
        const tx = gc.x_offset + col * stepW;
        const ty = gc.y_offset + row * stepH;
        if (tx >= 0 && tx <= stageW && ty >= 0 && ty <= stageH) {
          tiles.push({ tile_id: `tile_r${row}_c${col}`, row, col, x: tx, y: ty, w: fov.width, h: fov.height });
        }
      }
    }
    return tiles;
  });

  // ── Commands ─────────────────────────────────────────────

  async setOffset(xOffsetUm: number, yOffsetUm: number): Promise<void> {
    try {
      await this.#client.request('PATCH', '/session/grid', { x_offset: xOffsetUm, y_offset: yOffsetUm });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set grid offset');
    }
  }

  async setOverlap(overlapX: number, overlapY: number): Promise<void> {
    try {
      await this.#client.request('PATCH', '/session/grid', { overlap_x: overlapX, overlap_y: overlapY });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set grid overlap');
    }
  }

  /**
   * Snap the mosaic so the named edge of the current FOV position coincides
   * with the nearest tile boundary on that axis.
   */
  align(edge: AlignEdge, position?: { x: number; y: number }): void {
    const stage = this.#getStage();
    if (!stage) return;
    const stagePos = position ?? { x: stage.x.position?.value ?? 0, y: stage.y.position?.value ?? 0 };
    const { xOffsetUm, yOffsetUm } = computeAlignedOffset(
      edge,
      stagePos,
      { x: stage.x.lowerLimit?.value ?? 0, y: stage.y.lowerLimit?.value ?? 0 },
      { x: this.offsetX, y: this.offsetY },
      { x: this.spacingX, y: this.spacingY }
    );
    this.setOffset(xOffsetUm, yOffsetUm);
  }

  /** Stage position → mosaic cell index on the given axis. */
  positionToCell(position: number, axis: 'x' | 'y'): number {
    const stage = this.#getStage();
    if (!stage) return 0;
    const offset = axis === 'x' ? this.offsetX : this.offsetY;
    const spacing = axis === 'x' ? this.spacingX : this.spacingY;
    const lowerLimit = (axis === 'x' ? stage.x.lowerLimit?.value : stage.y.lowerLimit?.value) ?? 0;
    return Math.floor((position - lowerLimit - offset) / spacing);
  }

  /** Mosaic cell index → stage position on the given axis. */
  cellToPosition(cell: number, axis: 'x' | 'y'): number {
    const stage = this.#getStage();
    if (!stage) return 0;
    const offset = axis === 'x' ? this.offsetX : this.offsetY;
    const spacing = axis === 'x' ? this.spacingX : this.spacingY;
    const lowerLimit = (axis === 'x' ? stage.x.lowerLimit?.value : stage.y.lowerLimit?.value) ?? 0;
    return lowerLimit + offset + cell * spacing;
  }
}

// ── Pure helpers (exported for testing/reuse) ──────────────

/**
 * Compute new grid offsets that snap the tile grid to the current FOV position.
 *
 * Top/bottom snap Y only, left/right snap X only, center snaps both. Because
 * each tile spans exactly one FOV, aligning any edge on a given axis reduces
 * to the same operation: shift the offset so the nearest tile center coincides
 * with the FOV center on that axis. Directional names let users snap one axis
 * at a time (e.g. align sample's left edge, then independently align the top).
 *
 * All positions are in micrometers (µm).
 */
export function computeAlignedOffset(
  edge: AlignEdge,
  stagePos: { x: number; y: number },
  lowerLimit: { x: number; y: number },
  currentOffset: { x: number; y: number },
  spacing: { x: number; y: number }
): { xOffsetUm: number; yOffsetUm: number } {
  const fovX = stagePos.x - lowerLimit.x;
  const fovY = stagePos.y - lowerLimit.y;

  let x = currentOffset.x;
  let y = currentOffset.y;

  if (edge === 'left' || edge === 'right' || edge === 'center') {
    x = snapAxis(fovX, x, spacing.x);
  }
  if (edge === 'top' || edge === 'bottom' || edge === 'center') {
    y = snapAxis(fovY, y, spacing.y);
  }

  return { xOffsetUm: x, yOffsetUm: y };
}

/** Snap an offset so the nearest tile center lands on `fovCenter`. */
function snapAxis(fovCenter: number, offset: number, step: number): number {
  const r = (((fovCenter - offset) % step) + step) % step;
  const a = offset + r;
  const b = offset + r - step;
  return Math.abs(a - offset) <= Math.abs(b - offset) ? a : b;
}
