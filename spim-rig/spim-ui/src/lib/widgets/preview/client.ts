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

export interface PreviewIntensity {
	min: number; // Minimum intensity value (black level)
	max: number; // Maximum intensity value (white level)
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
	intensity: PreviewIntensity;
	fmt: 'jpeg' | 'png' | 'uint16'; // Frame format
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
 * Status update message from backend.
 */
interface PreviewStatusMessage {
	type: 'status';
	message: string;
	connected: boolean;
}

/**
 * Error message from backend.
 */
interface PreviewErrorMessage {
	type: 'error';
	error: string;
}

type PreviewMessage = PreviewFrameMessage | PreviewStatusMessage | PreviewErrorMessage;

/**
 * Control messages sent from client to server.
 */
type ControlMessage =
	| { type: 'start'; channels: string[] }
	| { type: 'stop' }
	| { type: 'transform'; transform: { x: number; y: number; k: number } };

export interface PreviewClientCallbacks {
	onFrame: (channel: string, metadata: PreviewFrameInfo, bitmap: ImageBitmap) => void;
	onStatus?: (connected: boolean, message: string) => void;
	onError?: (error: Error) => void;
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
					this.callbacks.onStatus?.(true, 'Connected');
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
					this.callbacks.onStatus?.(false, 'Disconnected');

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
	 * Handles incoming WebSocket messages (msgpack binary format).
	 */
	private async handleMessage(data: ArrayBuffer): Promise<void> {
		// Unpack msgpack binary message
		const message: PreviewMessage = unpack(new Uint8Array(data));

		switch (message.type) {
			case 'preview_frame':
				await this.handleFrameMessage(message);
				break;

			case 'status':
				this.callbacks.onStatus?.(message.connected, message.message);
				break;

			case 'error':
				this.callbacks.onError?.(new Error(message.error));
				break;

			default:
				console.warn('Unknown message type:', message);
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
	 * Starts preview streaming for specified channels.
	 */
	startPreview(channels: string[]): void {
		this.send({ type: 'start', channels });
	}

	/**
	 * Stops preview streaming.
	 */
	stopPreview(): void {
		this.send({ type: 'stop' });
	}

	/**
	 * Sends transform update to server (pan/zoom state).
	 */
	updateTransform(transform: { x: number; y: number; k: number }): void {
		this.send({ type: 'transform', transform });
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
