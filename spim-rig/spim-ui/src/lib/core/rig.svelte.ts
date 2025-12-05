import { browser } from '$app/environment';
import { RigClient, type DaqWaveforms } from './client.svelte';
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
	daq = $derived(this.#config?.daq);

	// DAQ waveforms (voltage arrays for each device)
	waveforms = $state<DaqWaveforms | null>(null);
	waveformsLoading = $state(false);

	// Magnification constant (TODO: make configurable)
	readonly #MAGNIFICATION = 1.0;

	constructor(id: string, config: ProfileConfig, channels: Record<string, ChannelConfig>, manager: RigManager) {
		this.id = id;
		this.#config = config;
		this.channels = channels;
		this.#manager = manager;
	}

	#getVec2DValue(deviceId: string, prop: string) {
		const val = this.#manager.devices.getPropertyValue(deviceId, prop);
		return Array.isArray(val) && val.length === 2 ? { x: val[0], y: val[1] } : null;
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

		const frameSizePx = this.#getVec2DValue(cameraId, 'frame_size_px');
		const pixelSizeUm = this.#getVec2DValue(cameraId, 'pixel_size_um');
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
	private wasDisconnected = false;
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

		// 3. Subscribe to DAQ waveforms updates
		this.subscribeToWaveforms();

		// 4. Fetch static configuration
		await this.fetchConfig();

		// 5. Initialize devices
		await this.devices.initialize();

		// 6. Request initial rig status
		this.rigClient.requestRigStatus();

		this.rigClient.requestWaveforms();
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
			const wasDisconnected = this.wasDisconnected;
			this.connected = connected;
			this.wasDisconnected = !connected;

			// Only refetch on REconnection (not initial connection)
			if (connected && wasDisconnected) {
				this.handleReconnection();
			}
		});

		// Subscribe to errors
		const unsubError = this.rigClient.onError((error) => {
			console.error('[RigManager] RigClient error:', error);
		});

		this.unsubscribers.push(unsubStatus, unsubConnection, unsubError);
	}

	/**
	 * Subscribe to DAQ waveforms updates.
	 */
	private subscribeToWaveforms() {
		const unsub = this.rigClient.on('daq/waveforms', (waveforms) => {
			this.handleWaveforms(waveforms);
		});
		this.unsubscribers.push(unsub);
	}

	/**
	 * Handle reconnection: refetch config and state when WebSocket reconnects.
	 */
	private async handleReconnection() {
		console.log('[RigManager] Reconnected - refetching data');

		try {
			// 1. Refetch configuration (profiles might have changed)
			await this.fetchConfig();

			// 2. Reinitialize devices (device state might have changed)
			await this.devices.initialize();

			// 3. Request current rig status (active profile, previewing state)
			this.rigClient.requestRigStatus();

			this.rigClient.requestWaveforms();

			// Clear any previous errors
			this.error = null;
		} catch (error) {
			console.error('[RigManager] Error during reconnection:', error);
			// Don't set error here - connection status is shown in ClientStatus
		}
	}

	/**
	 * Handle runtime state updates from rig/status WebSocket topic.
	 */
	private handleRigStatus(status: RigStatus) {
		const previousProfileId = this.activeProfileId;

		// Update runtime state only (not profiles/channels - those come from /config)
		if (!this.pendingLocalChange) {
			this.activeProfileId = status.active_profile_id;
		}
		this.previewing = status.previewing;

		// Request waveforms if profile changed or this is the initial status
		if (this.activeProfileId && this.activeProfileId !== previousProfileId) {
			this.requestWaveforms();
		}
	}

	/**
	 * Handle DAQ waveforms updates from daq/waveforms WebSocket topic.
	 */
	private handleWaveforms(waveforms: DaqWaveforms) {
		// Update the active profile's waveforms
		if (this.activeProfile) {
			this.activeProfile.waveforms = waveforms;
			this.activeProfile.waveformsLoading = false;
			console.log('[RigManager] Received waveforms for active profile:', Object.keys(waveforms));
		}
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

		// Mark waveforms as loading for the new profile
		const newProfile = this.profiles.find((p) => p.id === profileId);
		if (newProfile) {
			newProfile.waveformsLoading = true;
		}

		try {
			const response = await fetch(`${this.baseUrl}/profiles/active`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ profile_id: profileId })
			});

			if (!response.ok) {
				throw new Error(response.statusText);
			}

			const payload = await response.json();
			this.activeProfileId = payload.active_profile_id ?? profileId;

			// Request waveforms for the newly activated profile
			this.requestWaveforms();
		} catch (error) {
			console.error('[RigManager] Failed to activate profile:', error);

			// Clear loading state on error
			if (newProfile) {
				newProfile.waveformsLoading = false;
			}

			// Handle network errors separately - don't show in ProfileSelector
			if (error instanceof TypeError && error.message.includes('fetch')) {
				// Network error - let ClientStatus handle this
				console.error('[RigManager] Network error during profile activation');
			} else if (error instanceof Error) {
				// Profile-specific error - show in ProfileSelector
				this.error = error.message || 'Failed to activate profile';
			} else {
				this.error = 'Failed to activate profile';
			}
			throw error;
		} finally {
			this.pendingLocalChange = false;
			this.isMutating = false;
		}
	}

	/**
	 * Explicitly request waveforms for the active profile.
	 * Useful for on-demand loading when opening waveform viewer.
	 */
	requestWaveforms() {
		if (this.activeProfile) {
			this.activeProfile.waveformsLoading = true;
			this.rigClient.requestWaveforms();
			console.log('[RigManager] Requested waveforms for active profile');
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
