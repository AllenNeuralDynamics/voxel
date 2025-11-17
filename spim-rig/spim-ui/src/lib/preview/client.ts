import { unpack } from 'msgpackr';

/**
 * Backend contract types - messages from spim-rig backend.
 * These are packed with msgpack and sent over WebSocket.
 */

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
 * Preview frame message from backend (msgpack format).
 * Data field contains raw image bytes (JPEG, PNG, or raw pixel data).
 */
interface PreviewFrameMessage {
	type: 'preview_frame';
	channel: string;
	metadata: PreviewFrameInfo;
	data: ArrayBuffer; // Image data (JPEG bytes, PNG bytes, or raw pixels)
}

/**
 * Preview status message from backend (sent on connect and when status changes).
 * Contains all preview-related state.
 */
interface PreviewStatusMessage {
	type: 'preview_status';
	channels: string[];
	is_previewing: boolean;
}

/**
 * Error message from backend.
 */
interface PreviewErrorMessage {
	type: 'error';
	error: string;
}

interface PreviewCropMessage {
	type: 'crop';
	crop: PreviewCrop;
}

interface PreviewLevelsMessage {
	type: 'levels';
	channel: string;
	levels: PreviewLevels;
}

type PreviewMessage =
	| PreviewFrameMessage
	| PreviewStatusMessage
	| PreviewErrorMessage
	| PreviewCropMessage
	| PreviewLevelsMessage;

/**
 * Control messages sent from client to server.
 */
type ControlMessage =
	| { type: 'start' }
	| { type: 'stop' }
	| { type: 'crop'; crop: PreviewCrop }
	| { type: 'levels'; channel: string; levels: PreviewLevels };

export interface PreviewClientCallbacks {
	onPreviewStatus?: (channels: string[], is_previewing: boolean) => void;
	onFrame: (channel: string, info: PreviewFrameInfo, bitmap: ImageBitmap) => void;
	onError?: (error: Error) => void;
	onConnectionChange?: (connected: boolean) => void;
	onCropUpdate?: (crop: PreviewCrop) => void;
	onLevelsUpdate?: (channel: string, levels: PreviewLevels) => void;
}

/**
 * PreviewClient handles WebSocket communication for preview frame streaming.
 * Uses msgpack for efficient binary message encoding.
 * Provides automatic reconnection and frame decoding.
 */
export class PreviewClient {
	private ws: WebSocket | null = null;
	private reconnectAttempts = 0;
	private maxReconnectAttempts = 5;
	private reconnectDelay = 1000;
	private reconnectTimer: number | null = null;
	private shouldReconnect = true;

	constructor(
		private url: string,
		private callbacks: PreviewClientCallbacks
	) {}

	/**
	 * Connects to the preview WebSocket server.
	 * @returns Promise that resolves when connection is established
	 */
	connect(): Promise<void> {
		return new Promise((resolve, reject) => {
			try {
				this.ws = new WebSocket(this.url);
				this.ws.binaryType = 'arraybuffer'; // Receive binary data as ArrayBuffer

				this.ws.onopen = () => {
					console.log('Preview WebSocket connected');
					this.reconnectAttempts = 0;
					this.callbacks.onConnectionChange?.(true);
					resolve();
				};

				this.ws.onmessage = async (event) => {
					try {
						await this.handleMessage(event.data);
					} catch (error) {
						console.error('Error processing message:', error);
						this.callbacks.onError?.(error as Error);
					}
				};

				this.ws.onerror = (event) => {
					console.error('WebSocket error:', event);
					const error = new Error('WebSocket connection error');
					this.callbacks.onError?.(error);
					reject(error);
				};

				this.ws.onclose = (event) => {
					console.log('Preview WebSocket closed', event.code, event.reason);
					this.callbacks.onConnectionChange?.(false);

					if (this.shouldReconnect) {
						this.attemptReconnect();
					}
				};
			} catch (error) {
				reject(error);
			}
		});
	}

	/**
	 * Handles incoming WebSocket messages.
	 *
	 * Protocol:
	 * - JSON messages (string): Control messages (channels, status, error)
	 * - Hybrid binary messages: JSON envelope + newline + msgpack frame
	 */
	private async handleMessage(data: string | ArrayBuffer): Promise<void> {
		// Check if it's a string (JSON) or binary (hybrid)
		if (typeof data === 'string') {
			// JSON control message
			const message = JSON.parse(data) as PreviewMessage;

			switch (message.type) {
				case 'preview_status':
					this.callbacks.onPreviewStatus?.(message.channels, message.is_previewing);
					break;

				case 'error':
					this.callbacks.onError?.(new Error(message.error));
					break;

				case 'crop':
					this.callbacks.onCropUpdate?.(message.crop);
					break;

				case 'levels':
					this.callbacks.onLevelsUpdate?.(message.channel, message.levels);
					break;

				default:
					console.warn('Unknown JSON message type:', message);
			}
		} else {
			// Hybrid message: JSON envelope + newline + msgpack frame
			// Split at first newline
			const bytes = new Uint8Array(data);
			const newlineIndex = bytes.indexOf(10); // '\n' = 10

			if (newlineIndex === -1) {
				console.error('[PreviewClient] Invalid hybrid message: no newline separator');
				return;
			}

			// Parse JSON envelope
			const envelopeBytes = bytes.slice(0, newlineIndex);
			const envelopeText = new TextDecoder().decode(envelopeBytes);
			const envelope = JSON.parse(envelopeText) as { type: string; channel: string };

			// Unpack msgpack frame
			const frameBytes = bytes.slice(newlineIndex + 1);
			const frame = unpack(frameBytes) as {
				info: PreviewFrameInfo;
				data: ArrayBuffer;
			};

			if (!frame.info || !frame.data) {
				console.error('[PreviewClient] Invalid frame structure:', frame);
				return;
			}

			// Reconstruct as PreviewFrameMessage for handleFrameMessage
			const message: PreviewFrameMessage = {
				type: 'preview_frame',
				channel: envelope.channel,
				metadata: frame.info,
				data: frame.data
			};

			await this.handleFrameMessage(message);
		}
	}

	/**
	 * Decodes and processes a preview frame message.
	 */
	private async handleFrameMessage(message: PreviewMessage): Promise<void> {
		if (message.type !== 'preview_frame') return;

		// Determine MIME type from format
		let mimeType: string;
		switch (message.metadata.fmt) {
			case 'jpeg':
				mimeType = 'image/jpeg';
				break;
			case 'png':
				mimeType = 'image/png';
				break;
			case 'uint16':
				// Raw pixel data - will need special handling in the future
				console.warn('uint16 format not yet supported, skipping frame');
				return;
			default:
				console.warn('Unknown frame format:', message.metadata.fmt);
				return;
		}

		// Convert ArrayBuffer to Blob to ImageBitmap
		const blob = new Blob([message.data], { type: mimeType });
		const bitmap = await createImageBitmap(blob, {
			colorSpaceConversion: 'none'
		});

		// Debug logging for frame arrival order
		console.debug(
			`[Frame] channel=${message.channel} frame_idx=${message.metadata.frame_idx} crop={x:${message.metadata.crop.x.toFixed(3)}, y:${message.metadata.crop.y.toFixed(3)}, k:${message.metadata.crop.k.toFixed(3)}}`
		);

		this.callbacks.onFrame(message.channel, message.metadata, bitmap);
	}

	/**
	 * Attempts to reconnect to the WebSocket server.
	 */
	private attemptReconnect(): void {
		if (this.reconnectAttempts >= this.maxReconnectAttempts) {
			console.error('Max reconnection attempts reached');
			this.callbacks.onError?.(new Error('Failed to reconnect after multiple attempts'));
			return;
		}

		this.reconnectAttempts++;
		const delay = this.reconnectDelay * this.reconnectAttempts;
		console.log(`Reconnecting... attempt ${this.reconnectAttempts} in ${delay}ms`);

		this.reconnectTimer = window.setTimeout(() => {
			this.connect().catch((error) => {
				console.error('Reconnection failed:', error);
			});
		}, delay);
	}

	/**
	 * Sends a message to the server if connected (msgpack format).
	 */
	private send(message: ControlMessage): void {
		if (this.ws?.readyState === WebSocket.OPEN) {
			// For now, we'll send JSON for control messages
			// Backend can decide if it wants msgpack for these too
			this.ws.send(JSON.stringify(message));
		} else {
			console.warn('Cannot send message: WebSocket not connected');
		}
	}

	/**
	 * Starts preview streaming.
	 * Backend determines which channels to stream.
	 */
	startPreview(): void {
		this.send({ type: 'start' });
	}

	/**
	 * Stops preview streaming.
	 */
	stopPreview(): void {
		this.send({ type: 'stop' });
	}

	/**
	 * Sends crop update to server (pan/zoom state).
	 */
	updateCrop(crop: PreviewCrop): void {
		this.send({ type: 'crop', crop });
	}

	/**
	 * Sends levels update for a specific channel.
	 */
	updateChannelLevels(channel: string, levels: PreviewLevels): void {
		this.send({ type: 'levels', channel, levels: levels });
	}

	/**
	 * Disconnects from the WebSocket server.
	 */
	disconnect(): void {
		this.shouldReconnect = false;

		if (this.reconnectTimer !== null) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}

		if (this.ws) {
			this.ws.close();
			this.ws = null;
		}
	}

	/**
	 * Returns true if currently connected.
	 */
	get isConnected(): boolean {
		return this.ws?.readyState === WebSocket.OPEN;
	}
}
