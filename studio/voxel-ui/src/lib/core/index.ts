/**
 * Core infrastructure module.
 * Exports networking, device management, and type definitions.
 */

export { Client, type ClientOptions, type TopicHandlers } from './client.svelte.ts';
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
	VoxelRigConfig
} from './config.ts';

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

export type { PreviewCrop, PreviewFrameInfo, PreviewLevels } from './client.svelte.ts';

export type {
	AppStatus,
	AppPhase,
	SessionStatus,
	SessionRoot,
	SessionDirectory,
	RigMode,
	LogMessage,
	ErrorPayload,
	ProfileChangedPayload
} from './types.ts';
