export interface ControlReadyMessage {
	type: 'control:ready';
	timestamp: string;
}

export interface ControlProfileMessage {
	type: 'profiles:active_changed';
	active_profile_id: string | null;
	channels: string[];
	timestamp: string;
}

export type ControlMessage = ControlReadyMessage | ControlProfileMessage;

export interface ControlClientCallbacks {
	onReady?: (timestamp: string) => void;
	onProfileChanged?: (payload: ControlProfileMessage) => void;
	onConnectionChange?: (connected: boolean) => void;
	onError?: (error: Error) => void;
}

interface ControlClientOptions {
	autoReconnect?: boolean;
	initialReconnectDelayMs?: number;
	maxReconnectDelayMs?: number;
}

const DEFAULT_OPTIONS: Required<ControlClientOptions> = {
	autoReconnect: true,
	initialReconnectDelayMs: 2000,
	maxReconnectDelayMs: 15000
};

export class ControlClient {
	private ws: WebSocket | null = null;
	private reconnectDelay: number;
	private reconnectTimer: number | null = null;
	private shouldReconnect: boolean;

	constructor(
		private url: string,
		private callbacks: ControlClientCallbacks = {},
		options: ControlClientOptions = {}
	) {
		const resolved = { ...DEFAULT_OPTIONS, ...options };
		this.shouldReconnect = resolved.autoReconnect;
		this.reconnectDelay = resolved.initialReconnectDelayMs;
		this.maxReconnectDelay = resolved.maxReconnectDelayMs;
	}

	private readonly maxReconnectDelay: number;

	connect() {
		this.cleanupSocket();
		try {
			this.ws = new WebSocket(this.url);

			this.ws.onopen = () => {
				this.callbacks.onConnectionChange?.(true);
				this.reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;
			};

			this.ws.onmessage = (event) => {
				this.handleMessage(event.data);
			};

			this.ws.onerror = (event) => {
				const error = new Error('Control socket error');
				console.error('ControlClient error', event);
				this.callbacks.onError?.(error);
			};

			this.ws.onclose = () => {
				this.callbacks.onConnectionChange?.(false);
				if (this.shouldReconnect) {
					this.scheduleReconnect();
				}
			};
		} catch (error) {
			this.callbacks.onError?.(error as Error);
			this.scheduleReconnect();
		}
	}

	disconnect() {
		this.shouldReconnect = false;
		this.clearReconnectTimer();
		this.cleanupSocket();
		this.callbacks.onConnectionChange?.(false);
	}

	destroy() {
		this.disconnect();
	}

	private handleMessage(data: string | ArrayBuffer | Blob) {
		if (typeof data !== 'string') {
			return;
		}
		try {
			const message: ControlMessage = JSON.parse(data);
			if (message.type === 'control:ready') {
				this.callbacks.onReady?.(message.timestamp);
			} else if (message.type === 'profiles:active_changed') {
				this.callbacks.onProfileChanged?.(message);
			}
		} catch (error) {
			console.error('Failed to parse control message', error, data);
			this.callbacks.onError?.(error as Error);
		}
	}

	private scheduleReconnect() {
		if (!this.shouldReconnect || this.reconnectTimer) return;

		this.reconnectTimer = window.setTimeout(() => {
			this.reconnectTimer = null;
			this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
			this.connect();
		}, this.reconnectDelay);
	}

	private clearReconnectTimer() {
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
	}

	private cleanupSocket() {
		if (this.ws) {
			this.ws.onopen = null;
			this.ws.onclose = null;
			this.ws.onerror = null;
			this.ws.onmessage = null;
			this.ws.close();
			this.ws = null;
		}
	}
}
