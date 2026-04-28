/**
 * Wire schemas for the `session.*` topic namespace.
 *
 * Mirrors `vxl_web/protocol/session.py` on the backend.
 */

import type { JsonSchema } from './common';
import type { PreviewConfig } from './preview';
import type { DevicesSnapshot } from './device';
import type { GridConfig, PlanConfig, Stack } from './stacks';
import type { Waveform } from './waveform';

/** Storage path + pyramid level + compression. Embedded in `SessionStateUpdate.output`. */
export interface OutputConfig {
  store_path: string;
  max_level: number;
  compression: string;
}

/**
 * Device configuration (matches backend DeviceConfig from rigup.config)
 */
export interface DeviceConfig {
  target: string;
  init: Record<string, unknown>;
}

/**
 * Node configuration (matches backend NodeConfig from rigup.config)
 */
export interface NodeConfig {
  hostname: string;
  devices: Record<string, DeviceConfig>;
}

/**
 * Rig configuration (matches backend rigup.config.RigConfig).
 *
 * Contains hardware topology only: name, local devices, and remote nodes. AO devices
 * carry their own `ports` / `triggers` under `init`; there is no separate top-level
 * DAQ block on MicroscopeConfig.
 */
export interface RigConfig {
  name: string;
  devices: Record<string, DeviceConfig>;
  nodes?: Record<string, NodeConfig>;
}

/**
 * Stage configuration (matches backend StageConfig from voxel.config)
 */
export interface StageConfig {
  x: string;
  y: string;
  z: string;
}

/**
 * Optical path configuration base (matches backend from voxel.config)
 */
export interface OpticalPathConfig {
  aux_devices: string[];
}

/**
 * Detection path configuration (matches backend from voxel.config)
 */
export interface DetectionPathConfig extends OpticalPathConfig {
  filter_wheels: string[];
  magnification: number;
  rotation_deg: number;
}

/**
 * Illumination path configuration (matches backend from voxel.config)
 */
export type IlluminationPathConfig = OpticalPathConfig;

/**
 * Channel configuration - backend model (matches backend ChannelConfig from voxel.config)
 */
export interface ChannelConfig {
  label?: string | null;
  desc?: string;
  detection: string;
  illumination: string;
  filters: Record<string, string>;
  emission?: number | null;
}

// ==================== AO signals ====================
/**
 * Internal clock — AO device generates its own frame clock from (duration + rest_time).
 */
export interface InternalClock {
  type: 'internal';
}

/**
 * External clock — AO device listens for trigger edges on a logical input pin.
 * `source` is a key into the AO device's init-time `triggers` map.
 */
export interface ExternalClock {
  type: 'external';
  source: string;
}

export type ClockSource = InternalClock | ExternalClock;

/**
 * Declarative AO device configuration (matches backend AOSignals from voxel.analog_out.models).
 *
 * One per AO device referenced by a profile. The backend controller diffs against
 * its cached copy and picks the cheapest hardware path (no-op / hot-swap / rebuild).
 */
export interface AOSignals {
  sample_rate: number;
  duration: number;
  rest_time: number;
  clock_src: ClockSource;
  waveforms: Record<string, Waveform>;
}

// ==================== Profiles ====================

export interface SetupCommand {
  attr: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
}

/**
 * Profile configuration (matches backend ProfileConfig from voxel.config).
 *
 * `sync` is keyed by AO device UID — a profile may drive one or many AO devices,
 * each with its own timing and waveform set.
 */
export interface ProfileConfig {
  label?: string | null;
  desc: string;
  channels: string[];
  sync: Record<string, AOSignals>;
  props?: Record<string, Record<string, unknown>>;
  setup?: Record<string, SetupCommand[]>;
  rois?: Record<string, { x: number; y: number; w: number; h: number }>;
}

/**
 * Microscope configuration (matches backend MicroscopeConfig from voxel.config).
 */
export interface MicroscopeConfig {
  rig: RigConfig;
  stage: StageConfig;
  detection: Record<string, DetectionPathConfig>;
  illumination: Record<string, IlluminationPathConfig>;
  channels: Record<string, ChannelConfig>;
  profiles: Record<string, ProfileConfig>;
}

// ==================== Session-level config ====================

export interface SessionInfo {
  uid: string;
  name: string;
  description: string;
  source: string;
  created_at: string;
  created_by: string;
  hostname: string;
  data_root: string;
  data_path: string;
  collection: string;
  last_opened: string;
  open_count: number;
}

/**
 * Session-level config — extends `MicroscopeConfig` with session metadata + plan.
 * Matches backend `SessionConfig(MicroscopeConfig)` from `voxel.config`.
 */
export interface SessionConfig extends MicroscopeConfig {
  info: SessionInfo;
  metadata_schema: string;
  metadata: Record<string, unknown>;
  plan: Record<string, PlanConfig>;
  output: Record<string, OutputConfig>;
  grid: Record<string, GridConfig>;
  stacks: Record<string, Stack>;
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
