/**
 * Wire schemas for the `session.*` topic namespace.
 *
 * Mirrors `vxl_web/protocol/session.py` on the backend.
 */

import type { DeviceSnapshot } from '$lib/microscope/device';

import type { GridConfig, OutputConfig, PlanConfig, SessionConfig, Stack } from '../config';
import type { JsonSchema } from '../types';
import type { PreviewConfig } from './preview';

export interface DevicesSnapshot {
  devices: Record<string, DeviceSnapshot>;
  count: number;
}

export type SessionMode = 'idle' | 'previewing' | 'acquiring';

// ==================== Events ====================

export interface SessionStateUpdate {
  active_profile_id: string | null;
  mode: SessionMode;
  metadata: Record<string, unknown>;
  timestamp: string;
  plan: PlanConfig;
  output: OutputConfig;
  grid: GridConfig;
  stacks: Record<string, Stack>;
  stack_order: string[];
  fov: [number, number] | null;
  preview: Record<string, PreviewConfig>;
}

export interface SessionDetails {
  config: SessionConfig;
  metadata_schema: JsonSchema;
  devices: DevicesSnapshot;
}

export interface SessionEvents {
  'session.changed': SessionDetails;
}

// ==================== Commands ====================

// (none yet)
