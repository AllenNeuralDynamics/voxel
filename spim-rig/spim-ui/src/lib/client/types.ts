/**
 * Type definitions for the unified rig WebSocket service.
 * Uses slash-notation topics for routing (e.g., 'rig/status', 'preview/frame').
 */

/**
 * Base message structure for all WebSocket messages.
 */
export interface RigMessage {
	topic: string;
	payload?: unknown;
	channel?: string;
	timestamp?: string;
}

/**
 * Channel configuration (matches backend ChannelConfig).
 */
export interface ChannelConfig {
	label?: string | null;
	desc?: string;
	detection: string; // camera
	illumination: string; // laser
	filters: Record<string, string>;
}

/**
 * Profile configuration (matches backend ProfileConfig).
 */
export interface ProfileConfig {
	label?: string | null;
	desc: string;
	channels: string[]; // list of channel IDs
}

/**
 * Full rig status snapshot (sent on connect and on state changes).
 * Topic: 'rig/status'
 */
export interface RigStatusPayload {
	active_profile_id: string | null;
	profiles: Record<string, ProfileConfig>;
	channels: Record<string, ChannelConfig>;
	previewing: boolean;
	timestamp: string;
}

/**
 * Transform/crop state for pan/zoom.
 * Exported for use by manager and renderer.
 */
export interface PreviewCrop {
	x: number;
	y: number;
	k: number; // Zoom level: 0 = no zoom, 1 = max zoom
}

export interface PreviewLevels {
	min: number; // Minimum level value (black level)
	max: number; // Maximum level value (white level)
}

/**
 * Frame metadata from backend.
 * Exported for use in manager callbacks.
 */
export interface PreviewFrameInfo {
	frame_idx: number;
	preview_width: number;
	preview_height: number;
	full_width: number;
	full_height: number;
	crop: PreviewCrop;
	levels: PreviewLevels;
	fmt: 'jpeg' | 'png' | 'uint16'; // Frame format
	histogram?: number[]; // 256-bin histogram (0-255), only present in full frames
}
/**
 * Preview crop update payload.
 * Topic: 'preview/crop'
 */
export interface PreviewCropPayload {
	x: number;
	y: number;
	k: number;
}

/**
 * Preview levels update payload.
 * Topic: 'preview/levels'
 */
export interface PreviewLevelsPayload {
	channel: string;
	min: number;
	max: number;
}

/**
 * Error payload.
 * Topic: 'rig/error'
 */
export interface RigErrorPayload {
	error: string;
	topic?: string;
}

/**
 * PropertyModel matches pyrig.props.common.PropertyModel
 */
export interface PropertyModel {
	value: unknown;
	min_val?: number | null;
	max_val?: number | null;
	step?: number | null;
	options?: (string | number)[] | null;
}

/**
 * ErrorMsg matches pyrig.device.base.ErrorMsg
 */
export interface ErrorMsg {
	msg: string;
}

/**
 * Device property update payload.
 * Topic: 'device/property'
 * Matches PropsResponse from pyrig.device.base
 */
export interface DevicePropertyPayload {
	device: string;
	res: Record<string, PropertyModel>;
	err: Record<string, ErrorMsg>;
}

/**
 * Client-to-server message types.
 */
export type RigClientMessage =
	| { topic: 'profile/update'; payload: string } // profile_id
	| { topic: 'preview/start'; payload?: Record<string, never> }
	| { topic: 'preview/stop'; payload?: Record<string, never> }
	| { topic: 'preview/crop'; payload: PreviewCropPayload }
	| { topic: 'preview/levels'; payload: { channel: string; min: number; max: number } }
	| { topic: 'device/set_property'; payload: { device: string; properties: Record<string, unknown> } }
	| { topic: 'rig/request_status'; payload?: Record<string, never> };

/**
 * Message handler callback type.
 */
export type MessageHandler = (topic: string, payload: unknown) => void;

/**
 * Topic-specific handler types for type safety.
 */
export interface RigHandlers {
	'rig/status'?: (payload: RigStatusPayload) => void;
	'rig/error'?: (payload: RigErrorPayload) => void;
	'preview/status'?: (payload: PreviewStatusPayload) => void;
	'preview/frame'?: (channel: string, info: PreviewFrameInfo, bitmap: ImageBitmap) => void;
	'preview/crop'?: (payload: PreviewCropPayload) => void;
	'preview/levels'?: (payload: PreviewLevelsPayload) => void;
	'device/property'?: (payload: DevicePropertyPayload) => void;
}

/**
 * Preview status update payload.
 * Topic: 'preview/status'
 */
export interface PreviewStatusPayload {
	previewing: boolean;
	timestamp: string;
}

/**
 * Connection state callback.
 */
export type ConnectionHandler = (connected: boolean) => void;

/**
 * Error handler callback.
 */
export type ErrorHandler = (error: Error) => void;
