/**
 * Stack ordering strategy (matches backend StackOrder from voxel.stack)
 */
export type StackOrder =
  | 'sweep_row'
  | 'sweep_column'
  | 'snake_row'
  | 'snake_column'
  | 'nearest_neighbor'
  | 'optimized'
  | 'custom';

export const STACK_ORDER_OPTIONS: { value: StackOrder; label: string }[] = [
  { value: 'snake_row', label: 'Snake Row' },
  { value: 'snake_column', label: 'Snake Column' },
  { value: 'sweep_row', label: 'Sweep Row' },
  { value: 'sweep_column', label: 'Sweep Column' },
  { value: 'nearest_neighbor', label: 'Nearest Neighbor' },
  { value: 'optimized', label: 'Optimized' },
  { value: 'custom', label: 'Custom' }
];

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
  roll?: string;
  pitch?: string;
  yaw?: string;
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

// ==================== Clock source ====================

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

// ==================== Waveforms ====================

export interface BaseWaveform {
  voltage: { min: number; max: number };
  window: { min: number; max: number };
  rest_voltage?: number;
}

export interface PulseWaveform extends BaseWaveform {
  type: 'pulse';
}

export interface SquareWaveform extends BaseWaveform {
  type: 'square';
  duty_cycle: number;
  cycles?: number | null;
  frequency?: number | null;
  phase?: number;
}

export interface SineWaveform extends BaseWaveform {
  type: 'sine';
  frequency?: number | null;
  cycles?: number | null;
  phase?: number;
}

/**
 * Triangle waveform (matches backend TriangleWave from voxel.analog_out.wave).
 * The `type` literal accepts both `'triangle'` (canonical) and `'sawtooth'` (legacy).
 * `symmetry`: 1.0 = ramp up, 0.0 = ramp down, 0.5 = symmetric triangle.
 */
export interface TriangleWaveform extends BaseWaveform {
  type: 'triangle' | 'sawtooth';
  frequency?: number | null;
  cycles?: number | null;
  phase?: number;
  symmetry?: number;
}

export interface MultiPointWaveform extends BaseWaveform {
  type: 'multi_point';
  points: number[][];
}

export interface CSVWaveform extends BaseWaveform {
  type: 'csv';
  csv_file: string;
  directory?: string | null;
}

/**
 * Derived waveform variants — reference another channel by name and transform its output.
 * Serialized flat: `{ type: 'derived', operation: <op>, source: <channel>, ...op_fields }`.
 */
export interface DerivedMirror {
  type: 'derived';
  operation: 'mirror';
  source: string;
}

export interface DerivedScale {
  type: 'derived';
  operation: 'scale';
  source: string;
  factor: number;
}

export interface DerivedOffset {
  type: 'derived';
  operation: 'offset';
  source: string;
  delta: number;
}

export interface DerivedShift {
  type: 'derived';
  operation: 'shift';
  source: string;
  fraction: number;
}

export type DerivedWaveform = DerivedMirror | DerivedScale | DerivedOffset | DerivedShift;

/**
 * Full waveform union. Primitive variants carry their own shape; `DerivedWaveform`
 * references another channel by name.
 */
export type Waveform =
  | PulseWaveform
  | SquareWaveform
  | SineWaveform
  | TriangleWaveform
  | MultiPointWaveform
  | CSVWaveform
  | DerivedWaveform;

export function isDerivedWaveform(wf: Waveform): wf is DerivedWaveform {
  return wf.type === 'derived';
}

// ==================== AO signals ====================

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
