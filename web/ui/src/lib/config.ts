import type { Waveform } from '$lib/waveform';

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
