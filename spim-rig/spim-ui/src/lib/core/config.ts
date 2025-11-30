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
 * DAQ configuration (matches backend DaqConfig from spim_rig.config)
 */
export interface DaqConfig {
	device: string;
	acq_ports: Record<string, string>;
}

/**
 * Stage configuration (matches backend StageConfig from spim_rig.config)
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
 * Optical path configuration base (matches backend from spim_rig.config)
 */
export interface OpticalPathConfig {
	aux_devices: string[];
}

/**
 * Detection path configuration (matches backend from spim_rig.config)
 */
export interface DetectionPathConfig extends OpticalPathConfig {
	filter_wheels: string[];
}

/**
 * Illumination path configuration (matches backend from spim_rig.config)
 */
export type IlluminationPathConfig = OpticalPathConfig;

/**
 * Channel configuration - backend model (matches backend ChannelConfig from spim_rig.config)
 */
export interface ChannelConfig {
	label?: string | null;
	desc?: string;
	detection: string; // camera device ID
	illumination: string; // laser device ID
	filters: Record<string, string>; // filter_wheel_id -> position_label
}

/**
 * Profile configuration - backend model (matches backend ProfileConfig from spim_rig.config)
 */
export interface ProfileConfig {
	label?: string | null;
	desc: string;
	channels: string[]; // list of channel IDs
}

/**
 * Complete SPIM rig configuration (matches backend SpimRigConfig from spim_rig.config)
 */
export interface SpimRigConfig {
	metadata: RigMetadata;
	nodes: Record<string, NodeConfig>;
	daq: DaqConfig;
	stage: StageConfig;
	detection: Record<string, DetectionPathConfig>;
	illumination: Record<string, IlluminationPathConfig>;
	channels: Record<string, ChannelConfig>;
	profiles: Record<string, ProfileConfig>;
}
