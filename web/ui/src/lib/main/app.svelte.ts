import { browser } from '$app/environment';
import { Client, type ClientOptions } from './client.svelte';
import type { AppStatus, SessionDirectory, LogMessage, JsonSchema, VoxelRigConfig } from './types';
import { Session } from './session.svelte';
import { SvelteDate } from 'svelte/reactivity';

function getDefaultSocketUrl(): string {
	if (!browser) return 'ws://localhost:8000/ws';
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	return `${protocol}//${window.location.host}/ws`;
}

export interface AppOptions {
	socketUrl?: string;
	clientOptions?: ClientOptions;
}

const MAX_LOGS = 500;

export class App {
	readonly #client: Client;

	logs = $state<LogMessage[]>([]);
	status = $state<AppStatus | null>(null);
	error = $state<string | null>(null);
	session = $state<Session | null>(null);

	hasSession = $derived<boolean>(this.status?.session !== null && this.status?.session !== undefined);

	private wasDisconnected = false;
	private sessionInitializing = false;
	private unsubscribers: Array<() => void> = [];

	constructor(options: AppOptions = {}) {
		const socketUrl = options.socketUrl ?? getDefaultSocketUrl();
		this.#client = new Client(socketUrl, options.clientOptions);
	}

	get client(): Client {
		return this.#client;
	}

	// --- Lifecycle ---

	async initialize(): Promise<void> {
		this.#subscribeToTopics();
		await this.#client.connect();
		this.#client.requestStatus();
	}

	destroy(): void {
		if (this.session) {
			this.session.destroy();
			this.session = null;
		}
		this.unsubscribers.forEach((unsub) => unsub());
		this.unsubscribers = [];
		this.#client.destroy();
	}

	async retryConnection(): Promise<void> {
		this.status = null;
		await this.#client.connect();
		this.#client.requestStatus();
	}

	clearLogs(): void {
		this.logs = [];
	}

	// --- Session management (HTTP) ---

	async createSession(
		rootName: string,
		rigConfig: string,
		sessionName: string = '',
		metadataTarget?: string,
		metadata?: Record<string, unknown>
	): Promise<void> {
		if (!browser) return;
		if (this.hasSession) {
			throw new Error('A session is already active. Close it first.');
		}
		if (!this.status) {
			throw new Error('Cannot create session: not connected');
		}

		this.error = null;

		try {
			const body: Record<string, unknown> = {
				root_name: rootName,
				rig_config: rigConfig,
				session_name: sessionName
			};
			if (metadataTarget) body.metadata_target = metadataTarget;
			if (metadata) body.metadata = metadata;

			const response = await fetch(`${this.#client.baseUrl}/session/create`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({ detail: response.statusText }));
				throw new Error(errorData.detail || response.statusText);
			}

			console.debug('[App] Session create request sent');
		} catch (error) {
			console.error('[App] Failed to create session:', error);
			this.error = error instanceof Error ? error.message : 'Failed to create session';
			throw error;
		}
	}

	async resumeSession(sessionDir: string): Promise<void> {
		if (!browser) return;
		if (this.hasSession) {
			throw new Error('A session is already active. Close it first.');
		}

		this.error = null;

		try {
			const response = await fetch(`${this.#client.baseUrl}/session/resume`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ session_dir: sessionDir })
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({ detail: response.statusText }));
				throw new Error(errorData.detail || response.statusText);
			}

			console.debug('[App] Session resume request sent');
		} catch (error) {
			console.error('[App] Failed to resume session:', error);
			this.error = error instanceof Error ? error.message : 'Failed to resume session';
			throw error;
		}
	}

	async closeSession(): Promise<void> {
		if (!browser) return;
		if (!this.hasSession) {
			console.warn('[App] No active session to close');
			return;
		}

		this.error = null;

		try {
			const response = await fetch(`${this.#client.baseUrl}/session`, {
				method: 'DELETE'
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({ detail: response.statusText }));
				throw new Error(errorData.detail || response.statusText);
			}

			console.debug('[App] Session close request sent');
		} catch (error) {
			console.error('[App] Failed to close session:', error);
			this.error = error instanceof Error ? error.message : 'Failed to close session';
			throw error;
		}
	}

	// --- Read-only queries (work from idle) ---

	async fetchSessions(rootName: string): Promise<SessionDirectory[]> {
		try {
			const response = await fetch(`${this.#client.baseUrl}/roots/${encodeURIComponent(rootName)}/sessions`);
			if (!response.ok) {
				throw new Error(`Failed to fetch sessions: ${response.statusText}`);
			}
			const data = await response.json();
			return data.sessions ?? [];
		} catch (error) {
			console.error('[App] Failed to fetch sessions:', error);
			throw error;
		}
	}

	async fetchMetadataTargets(): Promise<Record<string, string>> {
		try {
			const response = await fetch(`${this.#client.baseUrl}/metadata/targets`);
			if (!response.ok) {
				throw new Error(`Failed to fetch metadata targets: ${response.statusText}`);
			}
			const data = await response.json();
			return data.targets ?? {};
		} catch (error) {
			console.error('[App] Failed to fetch metadata targets:', error);
			throw error;
		}
	}

	async fetchMetadataSchema(target: string): Promise<JsonSchema> {
		try {
			const response = await fetch(
				`${this.#client.baseUrl}/metadata/schema?target=${encodeURIComponent(target)}`
			);
			if (!response.ok) {
				throw new Error(`Failed to fetch metadata schema: ${response.statusText}`);
			}
			return await response.json();
		} catch (error) {
			console.error('[App] Failed to fetch metadata schema:', error);
			throw error;
		}
	}

	// --- Private: topic subscriptions ---

	#subscribeToTopics(): void {
		const unsubStatus = this.#client.on('status', (status) => {
			this.#handleStatusUpdate(status);
		});

		const unsubProfile = this.#client.on('profile/changed', (_payload) => {
			this.session?.requestWaveforms();
		});

		const unsubWaveforms = this.#client.on('daq/waveforms', (waveforms) => {
			this.session?.handleWaveforms(waveforms);
		});

		const unsubLogs = this.#client.on('log/message', (log) => {
			this.#handleLog(log);
		});

		const unsubError = this.#client.on('error', (payload) => {
			console.error('[App] Error from backend:', payload.error);
			this.#handleLog({
				level: 'error',
				message: payload.error,
				logger: 'backend',
				timestamp: new SvelteDate().toISOString()
			});
		});

		const unsubConnection = this.#client.onConnectionChange((connected) => {
			const wasDisconnected = this.wasDisconnected;
			this.wasDisconnected = !connected;

			if (connected && wasDisconnected) {
				this.#handleReconnection();
			}
		});

		this.unsubscribers.push(unsubStatus, unsubProfile, unsubWaveforms, unsubLogs, unsubError, unsubConnection);
	}

	async #handleStatusUpdate(status: AppStatus): Promise<void> {
		this.status = status;

		switch (status.phase) {
			case 'idle':
			case 'launching': {
				if (this.session) {
					this.session.destroy();
					this.session = null;
				}
				this.sessionInitializing = false;
				break;
			}

			case 'ready': {
				if (this.session) {
					this.session.updateStatus(status);
				} else if (!this.sessionInitializing) {
					this.sessionInitializing = true;
					try {
						await this.#initializeSession(status);
					} catch (e) {
						console.error('[App] Failed to initialize session:', e);
						this.error = e instanceof Error ? e.message : 'Failed to initialize session';
					} finally {
						this.sessionInitializing = false;
					}
				}
				break;
			}
		}
	}

	async #initializeSession(status: AppStatus): Promise<void> {
		const config = await this.#fetchConfig();
		if (!config) return;

		const session = new Session({
			client: this.#client,
			config,
			status
		});

		await session.initialize();
		this.session = session;
	}

	async #fetchConfig(): Promise<VoxelRigConfig | null> {
		try {
			const response = await fetch(`${this.#client.baseUrl}/config`);
			if (!response.ok) {
				throw new Error(`Failed to fetch config: ${response.statusText}`);
			}
			return await response.json();
		} catch (e) {
			console.error('[App] Failed to fetch config:', e);
			this.error = e instanceof Error ? e.message : 'Failed to fetch config';
			return null;
		}
	}

	#handleReconnection(): void {
		console.debug('[App] Reconnected - refetching data');
		this.#client.requestStatus();
	}

	#handleLog(log: LogMessage): void {
		this.logs = [...this.logs, log].slice(-MAX_LOGS);
	}
}
