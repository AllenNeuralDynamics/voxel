/**
 * Tile ordering pattern (matches backend TileOrder from voxel.config)
 */
export type TileOrder = 'row_wise' | 'column_wise' | 'snake_row' | 'snake_column';

/**
 * Global settings for acquisition planning (matches backend GlobalsConfig from voxel.config)
 */
export interface GlobalsConfig {
	default_overlap: number;
	default_tile_order: TileOrder;
}

/**
 * Device configuration (matches backend DeviceConfig from pyrig.config)
 */
export interface DeviceConfig {
	target: string;
	kwargs: Record<string, unknown>;
}

/**
 * Node configuration (matches backend NodeConfig from pyrig.config)
 */
export interface NodeConfig {
	hostname: string;
	devices: Record<string, DeviceConfig>;
}

/**
 * Rig metadata (matches backend RigMetadata from pyrig.config)
 */
export interface RigMetadata {
	name: string;
	control_port: number;
	log_port: number;
}

/**
 * DAQ configuration (matches backend DaqConfig from voxel.config)
 */
export interface DaqConfig {
	device: string;
	acq_ports: Record<string, string>;
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
	detection: string; // camera device ID
	illumination: string; // laser device ID
	filters: Record<string, string>; // filter_wheel_id -> position_label
	emission?: number | null; // Peak emission wavelength in nm
}

/**
 * Trigger configuration for DAQ timing (matches backend TriggerConfig from voxel.daq.acq_task)
 */
export interface TriggerConfig {
	pin: string;
	counter: string;
	duty_cycle: number; // 0.0 to 1.0
}

/**
 * Acquisition timing parameters (matches backend FrameTiming from voxel.sync_task)
 */
export interface FrameTiming {
	sample_rate: string; // Frequency with unit, e.g., "100 kHz"
	duration: string; // Time with unit, e.g., "0.1 s"
	rest_time: string; // Time with unit, e.g., "0 s"
	clock?: TriggerConfig | null;
}

/**
 * Waveform base interface
 */
export interface BaseWaveform {
	voltage: { min: number; max: number };
	window: { min: number; max: number };
	rest_voltage?: number;
}

/**
 * Pulse waveform (matches backend PulseWaveform from voxel.daq.wave)
 */
export interface PulseWaveform extends BaseWaveform {
	type: 'pulse';
}

/**
 * Square wave (matches backend SquareWave from voxel.daq.wave)
 */
export interface SquareWaveform extends BaseWaveform {
	type: 'square';
	duty_cycle: number;
	cycles?: number | null;
	frequency?: string | null; // Frequency with unit
}

/**
 * Sine wave (matches backend SineWave from voxel.daq.wave)
 */
export interface SineWaveform extends BaseWaveform {
	type: 'sine';
	frequency: string; // Frequency with unit
	phase?: number; // Radians
}

/**
 * Triangle wave (matches backend TriangleWave from voxel.daq.wave)
 */
export interface TriangleWaveform extends BaseWaveform {
	type: 'triangle';
	frequency: string; // Frequency with unit
	symmetry?: number; // 0.0 to 1.0
}

/**
 * Sawtooth wave (matches backend SawtoothWave from voxel.daq.wave)
 */
export interface SawtoothWaveform extends BaseWaveform {
	type: 'sawtooth';
	frequency: string; // Frequency with unit
	width?: number;
}

/**
 * Multi-point waveform (matches backend MultiPointWaveform from voxel.daq.wave)
 */
export interface MultiPointWaveform extends BaseWaveform {
	type: 'multi_point';
	points: number[][]; // Array of [time, voltage] pairs, normalized 0.0-1.0
}

/**
 * CSV waveform (matches backend CSVWaveform from voxel.daq.wave)
 */
export interface CSVWaveform extends BaseWaveform {
	type: 'csv';
	csv_file: string;
	directory?: string | null;
}

/**
 * Union type for all waveform types (matches backend Waveform from voxel.daq.wave)
 */
export type Waveform =
	| PulseWaveform
	| SquareWaveform
	| SineWaveform
	| TriangleWaveform
	| SawtoothWaveform
	| MultiPointWaveform
	| CSVWaveform;

/**
 * Sync task configuration (matches backend SyncTaskData from voxel.sync_task)
 */
export interface SyncTaskData {
	timing: FrameTiming;
	waveforms: Record<string, Waveform>; // device_id -> waveform
	stack_only?: string[]; // Waveforms excluded from frame streaming (included only during stack acquisition)
}

/**
 * Profile configuration - backend model (matches backend ProfileConfig from voxel.config)
 */
export interface ProfileConfig {
	label?: string | null;
	desc: string;
	channels: string[]; // list of channel IDs
	daq: SyncTaskData; // DAQ sync task configuration
}

/**
 * Complete Voxel rig configuration (matches backend VoxelRigConfig from voxel.config)
 */
export interface VoxelRigConfig {
	metadata: RigMetadata;
	globals: GlobalsConfig;
	nodes: Record<string, NodeConfig>;
	daq: DaqConfig;
	stage: StageConfig;
	detection: Record<string, DetectionPathConfig>;
	illumination: Record<string, IlluminationPathConfig>;
	channels: Record<string, ChannelConfig>;
	profiles: Record<string, ProfileConfig>;
}
