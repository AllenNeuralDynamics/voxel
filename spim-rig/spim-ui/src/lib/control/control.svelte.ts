import { browser } from '$app/environment';
import { SvelteURL } from 'svelte/reactivity';
import { ControlClient, type ControlProfileMessage } from '$lib/control/client';

export interface Channel {
	name: string;
	label?: string | null;
	desc: string;
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

export interface ProfileListResponse {
	profiles: Profile[];
	active_profile_id: string | null;
}

interface LoadProfilesOptions {
	force?: boolean;
}

export interface ProfilesManagerOptions {
	baseUrl?: string;
	controlSocketUrl?: string | null;
	autoLoad?: boolean;
	autoConnectControl?: boolean;
}

const DEFAULT_BASE_URL = 'http://localhost:8000';

function deriveControlSocketUrl(baseUrl: string): string | null {
	try {
		const url = new SvelteURL(baseUrl);
		url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
		url.pathname = '/ws/control';
		url.search = '';
		url.hash = '';
		return url.toString();
	} catch (error) {
		console.error('Failed to derive control WebSocket URL', error);
		return null;
	}
}

export class ProfilesManager {
	profiles = $state<Profile[]>([]);
	activeProfileId = $state<string | null>(null);
	error = $state<string | null>(null);
	isLoading = $state(false);
	isMutating = $state(false);
	controlConnected = $state(false);

	private baseUrl: string;
	private controlSocketUrl: string | null;
	private controlClient: ControlClient | null = null;
	private pendingLocalChange = false;

	constructor(options: ProfilesManagerOptions = {}) {
		this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, '');
		this.controlSocketUrl = options.controlSocketUrl ?? deriveControlSocketUrl(this.baseUrl);

		const shouldAutoLoad = options.autoLoad ?? browser;
		if (shouldAutoLoad) {
			void this.loadProfiles();
		}

		const shouldConnectControl = options.autoConnectControl ?? browser;
		if (shouldConnectControl && this.controlSocketUrl) {
			this.initControlClient();
		}
	}

	get activeProfile() {
		if (!this.activeProfileId) return null;
		return this.profiles.find((p) => p.id === this.activeProfileId) ?? null;
	}

	get hasProfiles(): boolean {
		return this.profiles.length > 0;
	}

	async loadProfiles({ force = false }: LoadProfilesOptions = {}) {
		if (!browser) return;
		if (this.isLoading && !force) return;

		this.error = null;
		this.isLoading = true;

		try {
			const response = await fetch(`${this.baseUrl}/profiles`);
			if (!response.ok) {
				throw new Error(`Failed to fetch profiles: ${response.statusText}`);
			}
			const data: ProfileListResponse = await response.json();
			this.profiles = data.profiles;
			this.activeProfileId = data.active_profile_id;
		} catch (error) {
			if (error instanceof Error) {
				this.error = error.message;
			} else {
				this.error = 'An unknown error occurred.';
			}
			console.error(error);
			throw error;
		} finally {
			this.isLoading = false;
		}
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
			await this.loadProfiles({ force: true });
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
		this.controlClient?.destroy();
		this.controlClient = null;
		this.controlConnected = false;
	}

	private initControlClient() {
		if (!browser || !this.controlSocketUrl) return;
		this.controlClient?.destroy();
		this.controlClient = new ControlClient(this.controlSocketUrl, {
			onConnectionChange: (connected) => {
				this.controlConnected = connected;
			},
			onProfileChanged: (message: ControlProfileMessage) => {
				this.activeProfileId = message.active_profile_id ?? null;
				if (!this.pendingLocalChange) {
					void this.loadProfiles({ force: true });
				}
			},
			onError: (error) => {
				console.error('Control client error', error);
			}
		});
		this.controlClient.connect();
	}
}
