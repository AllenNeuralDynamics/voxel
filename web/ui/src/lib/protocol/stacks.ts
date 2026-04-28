/**
 * Wire schemas for stacks + acquisition plan + per-stack progress.
 *
 * Mirrors `vxl_web/protocol/stacks.py` and the Stack model from `vxl.stack`.
 */

export type StackStatus = 'planned' | 'acquiring' | 'completed' | 'failed' | 'skipped';

export interface Stack {
  stack_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z_start: number;
  z_end: number;
  z_step: number;
  profile_id: string;
  status: StackStatus;
  num_frames: number;
  created_at: string;
  edited_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  skipped_at: string | null;
}

/** Result of one camera capture_batch call — matches backend BatchResult. */
export interface BatchResult {
  num_frames: number;
  started_at: string;
  completed_at: string;
  duration_s: number;
  dropped_frames: number;
}

/** Mosaic offsets + tile overlap. Embedded in `SessionStateUpdate.grid`. */
export interface GridConfig {
  x_offset: number;
  y_offset: number;
  /** 0.0 to 1.0 */
  overlap_x: number;
  /** 0.0 to 1.0 */
  overlap_y: number;
}

/** Stack ordering strategy — matches backend `StackOrder` from `voxel.stack`. */
export type StackOrder =
  | 'sweep_row'
  | 'sweep_column'
  | 'snake_row'
  | 'snake_column'
  | 'nearest_neighbor'
  | 'optimized'
  | 'custom';

/** Traversal order + per-stack defaults — matches backend PlanConfig. */
export interface PlanConfig {
  profile_order: string[];
  stack_order: StackOrder;
  sort_by_profile: boolean;
  z_step: number;
  default_z_start: number;
  default_z_end: number;
}

/** Per-stack acquisition progress — emitted on `acquisition.stack.progress`. */
export interface StackProgress {
  stack_id: string;
  status: StackStatus;
  expected_frames: number;
  timestamp: string;
  started_at: string;
  completed_at: string | null;
  channels: Record<string, BatchResult[]>;
  error_message: string | null;
}

export interface AcquisitionEvents {
  'acquisition.stack.progress': StackProgress;
}
