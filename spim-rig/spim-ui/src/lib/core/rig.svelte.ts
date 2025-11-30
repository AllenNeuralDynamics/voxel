import { browser } from '$app/environment';
import { RigClient } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type { RigStatus } from './client.svelte';
import type { SpimRigConfig, ProfileConfig, ChannelConfig } from './config';

const DEFAULT_BASE_URL = browser ? window.location.origin : 'http://localhost:8000';

export type Profile = {
	id: string;
	channels: Record<string, ChannelConfig>; // Expanded from string[] of channel IDs
} & Omit<ProfileConfig, 'channels'>;

/**
 * Options for RigManager construction
 */
export interface RigManagerOptions {
	socketUrl: string;
	baseUrl?: string;
}
/**
 * Unified manager for rig configuration and runtime state.
 *
 * Manages:
 * - RigClient (WebSocket connection)
 * - DevicesManager (device state and control)
 * - Static configuration (from GET /config): profiles, channels, stage, daq, detection, illumination, nodes, metadata
 * - Runtime state (from rig/status WebSocket): active_profile_id, previewing
 * - Profile mutations (via POST /profiles/active)
 */
export class RigManager {
	// Core services (owned by RigManager)
	private rigClient: RigClient;
	readonly devices: DevicesManager;

	// Static configuration
	config = $state<SpimRigConfig | null>(null);
	configLoading = $state(false);
	configError = $state<string | null>(null);

	// Runtime state
	activeProfileId = $state<string | null>(null);
	previewing = $state(false);

	// UI state
	error = $state<string | null>(null);
	isMutating = $state(false);
	connected = $state(false);

	readonly baseUrl: string;
	private pendingLocalChange = false;
	private unsubscribers: Array<() => void> = [];

	constructor(options: RigManagerOptions) {
		this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, '');
		this.rigClient = new RigClient(options.socketUrl);
		this.devices = new DevicesManager(this);
	}

	/**
	 * Access to RigClient for components that need WebSocket access (e.g., Previewer).
	 * Most components should use higher-level APIs instead.
	 */
	get client(): RigClient {
		return this.rigClient;
	}

	/**
	 * Initialize the RigManager: connect to WebSocket, fetch config, and initialize devices.
	 * Should be called once during app initialization.
	 */
	async initialize(): Promise<void> {
		// 1. Connect to WebSocket
		await this.rigClient.connect();

		// 2. Subscribe to rig status updates for runtime state
		this.subscribeToRigStatus();

		// 3. Fetch static configuration
		await this.fetchConfig();

		// 4. Initialize devices
		await this.devices.initialize();

		// 5. Request initial rig status
		this.rigClient.requestRigStatus();
	}

	// Derived state: build UI-friendly profiles from config
	get profiles(): Profile[] {
		if (!this.config) return [];

		return Object.entries(this.config.profiles).map(([profileId, profileConfig]: [string, ProfileConfig]) => {
			// Build channels for this profile
			const channels: Record<string, ChannelConfig> = {};
			for (const channelId of profileConfig.channels) {
				const channelConfig = this.config!.channels[channelId];
				if (channelConfig) {
					channels[channelId] = channelConfig;
				}
			}

			return {
				id: profileId,
				label: profileConfig.label,
				desc: profileConfig.desc,
				channels
			};
		});
	}

	get activeProfile(): Profile | null {
		if (!this.activeProfileId) return null;
		return this.profiles.find((p) => p.id === this.activeProfileId) ?? null;
	}

	get hasProfiles(): boolean {
		return this.profiles.length > 0;
	}

	// Convenience accessors for stage widget
	get stage() {
		return this.config?.stage;
	}

	get daq() {
		return this.config?.daq;
	}

	get stageAxisDeviceIds(): string[] {
		if (!this.stage) return [];
		const axes = [this.stage.x, this.stage.y, this.stage.z];
		if (this.stage.roll) axes.push(this.stage.roll);
		if (this.stage.pitch) axes.push(this.stage.pitch);
		if (this.stage.yaw) axes.push(this.stage.yaw);
		return axes;
	}

	/**
	 * Fetch static configuration from REST API.
	 * Should be called once during initialization.
	 */
	async fetchConfig() {
		this.configLoading = true;
		this.configError = null;

		try {
			const response = await fetch(`${this.baseUrl}/config`);

			if (!response.ok) {
				throw new Error(`Failed to fetch config: ${response.statusText}`);
			}

			this.config = await response.json();
		} catch (e) {
			this.configError = e instanceof Error ? e.message : 'Unknown error';
			console.error('Failed to fetch rig config:', e);
		} finally {
			this.configLoading = false;
		}
	}

	/**
	 * Subscribe to WebSocket rig/status for runtime state updates.
	 */
	private subscribeToRigStatus() {
		// Subscribe to rig status for runtime state updates
		const unsubStatus = this.rigClient.on('rig/status', (status) => {
			this.handleRigStatus(status);
		});

		// Subscribe to connection state
		const unsubConnection = this.rigClient.onConnectionChange((connected) => {
			this.connected = connected;
		});

		// Subscribe to errors
		const unsubError = this.rigClient.onError((error) => {
			console.error('[RigManager] RigClient error:', error);
			this.error = error.message;
		});

		this.unsubscribers.push(unsubStatus, unsubConnection, unsubError);
	}

	/**
	 * Handle runtime state updates from rig/status WebSocket topic.
	 */
	private handleRigStatus(status: RigStatus) {
		// Update runtime state only (not profiles/channels - those come from /config)
		if (!this.pendingLocalChange) {
			this.activeProfileId = status.active_profile_id;
		}
		this.previewing = status.previewing;
	}

	/**
	 * Activate a profile via REST API.
	 * WebSocket will notify us of the state change.
	 */
	async activateProfile(profileId: string) {
		if (!browser || !profileId) return;
		if (profileId === this.activeProfileId) return;

		this.error = null;
		this.isMutating = true;
		this.pendingLocalChange = true;

		try {
			const response = await fetch(`${this.baseUrl}/profiles/active`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ profile_id: profileId })
			});

			if (!response.ok) {
				throw new Error(`Failed to activate profile ${profileId}: ${response.statusText}`);
			}

			const payload = await response.json();
			this.activeProfileId = payload.active_profile_id ?? profileId;

			// The WebSocket will send us the updated rig/status, no need to manually reload
		} catch (error) {
			if (error instanceof Error) {
				this.error = error.message;
			} else {
				this.error = 'An unknown error occurred.';
			}
			console.error(error);
			throw error;
		} finally {
			this.pendingLocalChange = false;
			this.isMutating = false;
		}
	}

	destroy() {
		// Unsubscribe from all topics
		this.unsubscribers.forEach((unsub) => unsub());
		this.unsubscribers = [];

		// Cleanup owned services
		this.devices.destroy();
		this.rigClient.destroy();

		this.connected = false;
	}
}
