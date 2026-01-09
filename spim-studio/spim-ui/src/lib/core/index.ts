/**
 * Core rig management module.
 * Exports managers and types for rig communication and device control.
 */

export { RigClient } from './client.svelte.ts';
export { RigManager } from './rig.svelte.ts';
export { DevicesManager } from './devices.svelte.ts';
export type { DeviceInfo } from './devices.svelte.ts';

export type {
	DeviceConfig,
	NodeConfig,
	RigMetadata,
	DaqConfig,
	StageConfig,
	OpticalPathConfig,
	DetectionPathConfig,
	IlluminationPathConfig,
	ChannelConfig,
	ProfileConfig,
	SpimRigConfig
} from './config.ts';

export type { Profile, RigManagerOptions } from './rig.svelte.ts';

export type {
	DevicePropertyPayload,
	PropertyModel,
	ErrorMsg,
	PropertyInfo,
	ParamInfo,
	CommandInfo,
	DeviceInterface,
	DevicesResponse
} from './devices.svelte.ts';

export type { PreviewCrop, PreviewFrameInfo, PreviewLevels, RigStatus } from './client.svelte.ts';
