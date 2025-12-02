import { browser } from '$app/environment';
import { RigClient } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type { RigStatus } from './client.svelte';
import type { SpimRigConfig, ProfileConfig, ChannelConfig } from './config';

const DEFAULT_BASE_URL = browser ? window.location.origin : 'http://localhost:8000';

// export type Profile = {
// 	id: string;
// 	channels: Record<string, ChannelConfig>; // Expanded from string[] of channel IDs
// } & Omit<ProfileConfig, 'channels'>;

/**
 * Profile: Encapsulates profile configuration and derived state like FOV dimensions
 */
export class Profile {
	readonly id: string;
	readonly #manager: RigManager; // RigManager - can't import due to circular dependency

	// State
	#config = $state<ProfileConfig>();
	label = $derived(this.#config?.label);
	desc = $derived(this.#config?.desc);
	channels = $state<Record<string, ChannelConfig>>({});
	fovDimensions = $derived(this.#getfovDimensions());

	// Magnification constant (TODO: make configurable)
	readonly #MAGNIFICATION = 1.0;

	constructor(id: string, config: ProfileConfig, channels: Record<string, ChannelConfig>, manager: RigManager) {
		this.id = id;
		this.#config = config;
		this.channels = channels;
		this.#manager = manager;
	}

	#getFrameSizePx(cameraId: string) {
		const val = this.#manager.devices.getPropertyValue(cameraId, 'frame_size_px');
		return Array.isArray(val) && val.length === 2 ? { x: val[0], y: val[1] } : null;
	}

	#getPixelSizeUm(cameraId: string) {
		const val = this.#manager.devices.getPropertyValue(cameraId, 'pixel_size_um');

		// Handle different formats: "0.5, 0.5" string
		if (typeof val === 'string') {
			const parts = val.split(',').map((s) => parseFloat(s.trim()));
			if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
				return { x: parts[0], y: parts[1] };
			}
		}
		return null;
	}

	#getBinning(cameraId: string): number {
		const val = this.#manager.devices.getPropertyValue(cameraId, 'binning');
		return typeof val === 'number' && val > 0 ? val : 1;
	}

	// Calculate FOV dimensions in mm
	#getfovDimensions() {
		const firstChannel = Object.values(this.channels)[0];
		const cameraId = firstChannel?.detection ?? null;
		if (!cameraId) return null;

		const frameSizePx = this.#getFrameSizePx(cameraId);
		const pixelSizeUm = this.#getPixelSizeUm(cameraId);
		const binning = this.#getBinning(cameraId);

		if (!frameSizePx || !pixelSizeUm) {
			return { width: 5, height: 5 }; // Fallback to 5mm
		}

		// FOV (mm) = (pixels * pixel_size_um * binning) / (1000 * magnification)
		// Note: frame_size_px already accounts for binning (roi dimensions / binning)
		// So we multiply by binning to get the actual physical size
		const width = (frameSizePx.x * pixelSizeUm.x * binning) / (1000 * this.#MAGNIFICATION);
		const height = (frameSizePx.y * pixelSizeUm.y * binning) / (1000 * this.#MAGNIFICATION);

		return { width, height };
	}
}

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

	// Profiles (state)
	profiles = $state<Profile[]>([]);

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

	// Build Profile instances from config
	private buildProfiles() {
		if (!this.config) {
			this.profiles = [];
			return;
		}

		this.profiles = Object.entries(this.config.profiles).map(([profileId, profileConfig]: [string, ProfileConfig]) => {
			// Build channels for this profile
			const channels: Record<string, ChannelConfig> = {};
			for (const channelId of profileConfig.channels) {
				const channelConfig = this.config!.channels[channelId];
				if (channelConfig) {
					channels[channelId] = channelConfig;
				}
			}

			return new Profile(profileId, profileConfig, channels, this);
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

			// Build Profile instances from config
			this.buildProfiles();
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
