/**
 * Unified WebSocket client for rig communication.
 * Uses slash-notation topics for routing and multiplexing.
 */

import { unpack } from 'msgpackr';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import type {
	RigMessage,
	MessageHandler,
	ConnectionHandler,
	ErrorHandler,
	RigClientMessage,
	RigHandlers,
	PreviewFrameInfo
} from './types';

interface RigClientOptions {
	autoReconnect?: boolean;
	initialReconnectDelayMs?: number;
	maxReconnectDelayMs?: number;
	maxReconnectAttempts?: number;
}

const DEFAULT_OPTIONS: Required<RigClientOptions> = {
	autoReconnect: true,
	initialReconnectDelayMs: 1000,
	maxReconnectDelayMs: 15000,
	maxReconnectAttempts: 10
};

export class RigClient {
	private ws: WebSocket | null = null;
	private handlers = new SvelteMap<string, SvelteSet<MessageHandler>>();
	private reconnectAttempts = 0;
	private reconnectDelay: number;
	private reconnectTimer: number | null = null;
	private shouldReconnect: boolean;
	private readonly maxReconnectDelay: number;
	private readonly maxReconnectAttempts: number;
	private connectionHandlers = new SvelteSet<ConnectionHandler>();
	private errorHandlers = new SvelteSet<ErrorHandler>();

	statusMessage = $state('Idle');

	constructor(
		private url: string,
		options: RigClientOptions = {}
	) {
		const resolved = { ...DEFAULT_OPTIONS, ...options };
		this.shouldReconnect = resolved.autoReconnect;
		this.reconnectDelay = resolved.initialReconnectDelayMs;
		this.maxReconnectDelay = resolved.maxReconnectDelayMs;
		this.maxReconnectAttempts = resolved.maxReconnectAttempts;
	}

	/**
	 * Connect to the WebSocket server.
	 */
	connect(): Promise<void> {
		this.statusMessage = 'Connecting...';
		return new Promise((resolve, reject) => {
			try {
				this.cleanupSocket();
				this.ws = new WebSocket(this.url);
				this.ws.binaryType = 'arraybuffer';

				this.ws.onopen = () => {
					console.log('[RigClient] Connected');
					this.statusMessage = 'Connected';
					this.reconnectAttempts = 0;
					this.reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;
					this.notifyConnectionChange(true);
					resolve();
				};

				this.ws.onmessage = async (event) => {
					try {
						await this.handleMessage(event.data);
					} catch (error) {
						console.error('[RigClient] Error processing message:', error);
						this.notifyError(error as Error);
					}
				};

				this.ws.onerror = (event) => {
					console.error('[RigClient] WebSocket error:', event);
					const error = new Error('WebSocket connection error');
					this.statusMessage = 'Connection error';
					this.notifyError(error);
					reject(error);
				};

				this.ws.onclose = (event) => {
					console.log('[RigClient] Connection closed:', event.code, event.reason);
					this.statusMessage = 'Disconnected';
					this.notifyConnectionChange(false);

					if (this.shouldReconnect) {
						this.scheduleReconnect();
					}
				};
			} catch (error) {
				this.statusMessage = 'Failed to connect';
				reject(error);
			}
		});
	}

	/**
	 * Disconnect from the WebSocket server.
	 */
	disconnect(): void {
		this.shouldReconnect = false;
		this.clearReconnectTimer();
		this.cleanupSocket();
		this.notifyConnectionChange(false);
		this.statusMessage = 'Disconnected';
	}

	/**
	 * Subscribe to messages matching a topic pattern.
	 * Supports exact matches, prefix matches, and wildcard '*'.
	 *
	 * @param pattern - Topic pattern to match (e.g., 'preview', 'preview/frame', '*')
	 * @param handler - Callback function
	 * @returns Unsubscribe function
	 *
	 * @example
	 * // Subscribe to all preview events
	 * const unsub = client.subscribe('preview', (topic, payload) => {
	 *   console.log(topic, payload);
	 * });
	 *
	 * // Subscribe to specific event
	 * client.subscribe('preview/frame', (topic, payload) => { ... });
	 *
	 * // Subscribe to everything
	 * client.subscribe('*', (topic, payload) => { ... });
	 */
	subscribe(pattern: string, handler: MessageHandler): () => void {
		if (!this.handlers.has(pattern)) {
			this.handlers.set(pattern, new SvelteSet());
		}
		this.handlers.get(pattern)!.add(handler);

		return () => this.unsubscribe(pattern, handler);
	}

	/**
	 * Unsubscribe a handler from a topic pattern.
	 */
	unsubscribe(pattern: string, handler: MessageHandler): void {
		const handlers = this.handlers.get(pattern);
		if (handlers) {
			handlers.delete(handler);
			if (handlers.size === 0) {
				this.handlers.delete(pattern);
			}
		}
	}

	/**
	 * Type-safe subscription methods for specific topics.
	 */
	on<K extends keyof RigHandlers>(topic: K, handler: RigHandlers[K]): () => void {
		// Special case for preview/frame which has different signature
		if (topic === 'preview/frame') {
			return this.subscribe(topic, handler as MessageHandler);
		}
		return this.subscribe(topic, (t, payload) => {
			// Type assertion is safe here because we know the payload type matches the handler
			(handler as (payload: unknown) => void)(payload);
		});
	}

	/**
	 * Subscribe to connection state changes.
	 */
	onConnectionChange(handler: ConnectionHandler): () => void {
		this.connectionHandlers.add(handler);
		return () => this.connectionHandlers.delete(handler);
	}

	/**
	 * Subscribe to errors.
	 */
	onError(handler: ErrorHandler): () => void {
		this.errorHandlers.add(handler);
		return () => this.errorHandlers.delete(handler);
	}

	/**
	 * Send a message to the server.
	 */
	send(message: RigClientMessage): void {
		if (this.ws?.readyState === WebSocket.OPEN) {
			this.ws.send(JSON.stringify(message));
		} else {
			console.warn('[RigClient] Cannot send message: not connected');
		}
	}

	/**
	 * Convenience methods for common operations.
	 */

	startPreview(): void {
		this.send({ topic: 'preview/start' });
	}

	stopPreview(): void {
		this.send({ topic: 'preview/stop' });
	}

	updateCrop(x: number, y: number, k: number): void {
		this.send({ topic: 'preview/crop', payload: { x, y, k } });
	}

	updateLevels(channel: string, min: number, max: number): void {
		this.send({ topic: 'preview/levels', payload: { channel, min, max } });
	}

	/**
	 * Check if currently connected.
	 */
	get isConnected(): boolean {
		return this.ws?.readyState === WebSocket.OPEN;
	}

	/**
	 * Handle incoming WebSocket messages.
	 */
	private async handleMessage(data: string | ArrayBuffer): Promise<void> {
		// JSON message
		if (typeof data === 'string') {
			const message = JSON.parse(data) as RigMessage;
			this.dispatch(message.topic, message.payload);
			return;
		}

		// Binary message (hybrid format for preview frames)
		// Format: JSON envelope + newline + msgpack frame
		const bytes = new Uint8Array(data);
		const newlineIndex = bytes.indexOf(10); // '\n' = 10

		if (newlineIndex === -1) {
			console.error('[RigClient] Invalid hybrid message: no newline separator');
			return;
		}

		// Parse JSON envelope
		const envelopeBytes = bytes.slice(0, newlineIndex);
		const envelopeText = new TextDecoder().decode(envelopeBytes);
		const envelope = JSON.parse(envelopeText) as { topic: string; channel: string };

		// Unpack msgpack frame
		const frameBytes = bytes.slice(newlineIndex + 1);
		const frame = unpack(frameBytes) as {
			info: PreviewFrameInfo;
			data: ArrayBuffer;
		};

		if (!frame.info || !frame.data) {
			console.error('[RigClient] Invalid frame structure:', frame);
			return;
		}

		// Decode frame to ImageBitmap
		const bitmap = await this.decodeFrame(frame.info.fmt, frame.data);
		if (bitmap) {
			// Dispatch with channel, info, and bitmap
			this.dispatchFrame(envelope.topic, envelope.channel, frame.info, bitmap);
		}
	}

	/**
	 * Decode frame data to ImageBitmap.
	 */
	private async decodeFrame(fmt: 'jpeg' | 'png' | 'uint16', data: ArrayBuffer): Promise<ImageBitmap | null> {
		let mimeType: string;

		switch (fmt) {
			case 'jpeg':
				mimeType = 'image/jpeg';
				break;
			case 'png':
				mimeType = 'image/png';
				break;
			case 'uint16':
				console.warn('[RigClient] uint16 format not yet supported');
				return null;
			default:
				console.warn('[RigClient] Unknown frame format:', fmt);
				return null;
		}

		const blob = new Blob([data], { type: mimeType });
		return await createImageBitmap(blob, { colorSpaceConversion: 'none' });
	}

	/**
	 * Dispatch a message to all matching handlers.
	 * Supports exact match, prefix match, and wildcard '*'.
	 */
	private dispatch(topic: string, payload: unknown): void {
		// Exact match
		this.handlers.get(topic)?.forEach((h) => h(topic, payload));

		// Prefix matching: 'preview' matches 'preview/frame'
		const parts = topic.split('/');
		for (let i = parts.length - 1; i > 0; i--) {
			const prefix = parts.slice(0, i).join('/');
			this.handlers.get(prefix)?.forEach((h) => h(topic, payload));
		}

		// Wildcard: '*' matches everything
		this.handlers.get('*')?.forEach((h) => h(topic, payload));
	}

	/**
	 * Dispatch a preview frame to handlers.
	 */
	private dispatchFrame(topic: string, channel: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void {
		// For preview/frame, we pass channel, info, and bitmap as separate args
		const handlers = this.handlers.get(topic);
		if (handlers) {
			handlers.forEach((h) => h(topic, { channel, info, bitmap }));
		}

		// Also dispatch to prefix handlers
		const parts = topic.split('/');
		for (let i = parts.length - 1; i > 0; i--) {
			const prefix = parts.slice(0, i).join('/');
			this.handlers.get(prefix)?.forEach((h) => h(topic, { channel, info, bitmap }));
		}

		// Wildcard
		this.handlers.get('*')?.forEach((h) => h(topic, { channel, info, bitmap }));
	}

	/**
	 * Notify all connection handlers of a state change.
	 */
	private notifyConnectionChange(connected: boolean): void {
		for (const h of this.connectionHandlers) {
			h(connected);
		}
	}

	/**
	 * Notify all error handlers.
	 */
	private notifyError(error: Error): void {
		this.statusMessage = error.message;
		for (const h of this.errorHandlers) {
			h(error);
		}
	}

	/**
	 * Schedule a reconnection attempt.
	 */
	private scheduleReconnect(): void {
		if (!this.shouldReconnect || this.reconnectTimer) {
			return;
		}

		if (this.reconnectAttempts >= this.maxReconnectAttempts) {
			console.error('[RigClient] Max reconnection attempts reached');
			this.statusMessage = 'Reconnection failed';
			this.notifyError(new Error('Failed to reconnect after multiple attempts'));
			return;
		}

		this.reconnectAttempts++;
		this.statusMessage = `Reconnecting... (attempt ${this.reconnectAttempts})`;
		console.log(`[RigClient] Reconnecting... attempt ${this.reconnectAttempts} in ${this.reconnectDelay}ms`);

		this.reconnectTimer = window.setTimeout(() => {
			this.reconnectTimer = null;
			this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
			this.connect().catch((error) => {
				console.error('[RigClient] Reconnection failed:', error);
			});
		}, this.reconnectDelay);
	}

	/**
	 * Clear the reconnection timer.
	 */
	private clearReconnectTimer(): void {
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
	}

	/**
	 * Clean up the WebSocket connection.
	 */
	private cleanupSocket(): void {
		if (this.ws) {
			this.ws.onopen = null;
			this.ws.onclose = null;
			this.ws.onerror = null;
			this.ws.onmessage = null;
			this.ws.close();
			this.ws = null;
		}
	}

	/**
	 * Clean up all resources.
	 */
	destroy(): void {
		this.disconnect();
		this.handlers.clear();
		this.connectionHandlers.clear();
		this.errorHandlers.clear();
	}
}
