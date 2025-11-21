/**
 * Unified rig WebSocket client module.
 * Exports client, types, and utilities for rig communication.
 */

export { RigClient } from './client.svelte.ts';
export type {
	RigMessage,
	RigStatusPayload,
	PreviewCropPayload,
	PreviewLevelsPayload,
	RigErrorPayload,
	RigClientMessage,
	MessageHandler,
	RigHandlers,
	ConnectionHandler,
	ErrorHandler,
	PreviewFrameInfo,
	PreviewCrop,
	PreviewLevels,
	DevicePropertyPayload,
	ChannelConfig
} from './types';

export { default as ClientStatus } from './ClientStatus.svelte';
