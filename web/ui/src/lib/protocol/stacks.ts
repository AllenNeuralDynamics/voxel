/**
 * Wire schemas for stacks + acquisition plan + per-stack progress.
 *
 * Mirrors `vxl_web/protocol/stacks.py` and the Stack model from `vxl.stack`.
 */

import type { StackStatus } from '../config';

/** Result of one camera capture_batch call — matches backend BatchResult. */
export interface BatchResult {
  num_frames: number;
  started_at: string;
  completed_at: string;
  duration_s: number;
  dropped_frames: number;
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
