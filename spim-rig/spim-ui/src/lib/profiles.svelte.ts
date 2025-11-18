import { browser } from '$app/environment';
import type { RigClient, RigStatusPayload } from '$lib/client';

export interface Channel {
	id: string;
	label?: string | null;
	desc?: string;
	laser: string;
	filter: string;
	camera: string;
}

export interface Profile {
	id: string;
	label?: string | null;
	desc: string;
	channels: Record<string, Channel>;
}

export interface ProfilesManagerOptions {
	rigClient: RigClient;
	baseUrl?: string;
}

const DEFAULT_BASE_URL = 'http://localhost:8000';

export class ProfilesManager {
	profiles = $state<Profile[]>([]);
	activeProfileId = $state<string | null>(null);
	error = $state<string | null>(null);
	isMutating = $state(false);
	connected = $state(false);

	private baseUrl: string;
	private rigClient: RigClient;
	private pendingLocalChange = false;
	private unsubscribers: Array<() => void> = [];

	constructor(options: ProfilesManagerOptions) {
		this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, '');
		this.rigClient = options.rigClient;

		// Subscribe to rig status updates
		this.subscribeToRigStatus();
	}

	get activeProfile() {
		if (!this.activeProfileId) return null;
		return this.profiles.find((p) => p.id === this.activeProfileId) ?? null;
	}

	get hasProfiles(): boolean {
		return this.profiles.length > 0;
	}

	private subscribeToRigStatus() {
		// Subscribe to rig status for profile updates
		const unsubStatus = this.rigClient.on('rig/status', (status) => {
			this.handleRigStatus(status);
		});

		// Subscribe to connection state
		const unsubConnection = this.rigClient.onConnectionChange((connected) => {
			this.connected = connected;
		});

		// Subscribe to errors
		const unsubError = this.rigClient.onError((error) => {
			console.error('[ProfilesManager] RigClient error:', error);
			this.error = error.message;
		});

		this.unsubscribers.push(unsubStatus, unsubConnection, unsubError);
	}

	private handleRigStatus(status: RigStatusPayload) {
		// Update active profile ID
		if (!this.pendingLocalChange) {
			this.activeProfileId = status.active_profile_id;
		}

		// Convert backend format to UI format
		this.profiles = Object.entries(status.profiles).map(([profileId, profileConfig]) => {
			// Build channels for this profile
			const channels: Record<string, Channel> = {};
			for (const channelId of profileConfig.channels) {
				const channelConfig = status.channels[channelId];
				if (channelConfig) {
					channels[channelId] = {
						id: channelId,
						label: channelConfig.label,
						desc: channelConfig.desc,
						laser: channelConfig.excitation,
						filter: channelConfig.filter_,
						camera: channelConfig.detection
					};
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
		this.connected = false;
	}
}
