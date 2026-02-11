import { browser } from '$app/environment';
import { Client, type ClientOptions, type DaqWaveforms } from '../core/client.svelte.ts';
import { DevicesManager } from '../core/devices.svelte.ts';
import {
	parseVec2D,
	type AppStatus,
	type SessionDirectory,
	type LogMessage,
	type GridConfig,
	type Tile,
	type Stack,
	type LayerVisibility,
	type TileOrder,
	type Vec2D,
	type JsonSchema
} from '../core/types.ts';
import type { VoxelRigConfig, ProfileConfig, ChannelConfig } from '../core/config.ts';
import { fetchColormapCatalog, type ColormapCatalog } from '../core/colormaps.ts';
import { PreviewState } from './preview.svelte.ts';
import { Axis } from './axis.svelte.ts';
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

export class Profile {
	readonly id: string;
	readonly #app: App;

	#config = $state<ProfileConfig>();
	label = $derived(this.#config?.label);
	desc = $derived(this.#config?.desc);
	channels = $state<Record<string, ChannelConfig>>({});
	fovDimensions = $derived(this.#getfovDimensions());
	daq = $derived(this.#config?.daq);

	waveforms = $state<DaqWaveforms | null>(null);
	waveformsLoading = $state(false);

	constructor(id: string, config: ProfileConfig, channels: Record<string, ChannelConfig>, app: App) {
		this.id = id;
		this.#config = config;
		this.channels = channels;
		this.#app = app;
	}

	#getVec2DValue(deviceId: string, prop: string): Vec2D | null {
		const val = this.#app.devices.getPropertyValue(deviceId, prop);
		return parseVec2D(val);
	}

	#getMagnification(cameraId: string): number {
		const detectionConfig = this.#app.config?.detection?.[cameraId];
		return detectionConfig?.magnification ?? 1.0;
	}

	#getfovDimensions() {
		const firstChannel = Object.values(this.channels)[0];
		const cameraId = firstChannel?.detection ?? null;
		if (!cameraId) return null;

		const frameSizePx = this.#getVec2DValue(cameraId, 'frame_size_px');
		const pixelSizeUm = this.#getVec2DValue(cameraId, 'pixel_size_um');
		const magnification = this.#getMagnification(cameraId);

		if (!frameSizePx || !pixelSizeUm) {
			return { width: 5, height: 5 };
		}

		const width = (frameSizePx.x * pixelSizeUm.x) / (1000 * magnification);
		const height = (frameSizePx.y * pixelSizeUm.y) / (1000 * magnification);

		return { width, height };
	}
}

export class App {
	readonly #client: Client;
	readonly devices: DevicesManager;

	previewState = $state<PreviewState | null>(null);

	xAxis = $state<Axis | null>(null);
	yAxis = $state<Axis | null>(null);
	zAxis = $state<Axis | null>(null);

	stageWidth = $derived(this.xAxis?.range ?? 100);
	stageHeight = $derived(this.yAxis?.range ?? 100);
	stageDepth = $derived(this.zAxis?.range ?? 100);
	stageIsMoving = $derived(this.xAxis?.isMoving || this.yAxis?.isMoving || this.zAxis?.isMoving);
	stageConnected = $derived((this.xAxis?.isConnected && this.yAxis?.isConnected && this.zAxis?.isConnected) ?? false);

	logs = $state<LogMessage[]>([]);
	status = $state<AppStatus | null>(null);
	activeProfileId = $derived<string | null>(this.status?.session?.active_profile_id ?? null);
	hasSession = $derived<boolean>(this.status?.session !== null && this.status?.session !== undefined);
	connectionError = $state<string | null>(null);

	config = $state<VoxelRigConfig | null>(null);
	configLoading = $state(false);
	configError = $state<string | null>(null);

	colormapCatalog = $state<ColormapCatalog>([]);
	profiles = $state<Profile[]>([]);

	error = $state<string | null>(null);
	isMutating = $state(false);

	gridConfig = $derived<GridConfig>(
		this.status?.session?.grid_config ?? {
			x_offset_um: 0,
			y_offset_um: 0,
			overlap: 0.1,
			z_step_um: 2.0,
			default_z_start_um: 0,
			default_z_end_um: 100
		}
	);
	tiles = $derived<Tile[]>(this.status?.session?.tiles ?? []);
	stacks = $derived<Stack[]>(this.status?.session?.stacks ?? []);
	tileOrder = $derived<TileOrder>(this.status?.session?.tile_order ?? 'snake_row');

	layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true });

	#selectedTilePos = $state<[number, number]>([0, 0]);
	selectedTile = $derived<Tile>(this.#getSelectedTile());
	selectedStack = $derived<Stack | null>(
		this.stacks.find((s) => s.row === this.selectedTile.row && s.col === this.selectedTile.col) ?? null
	);

	private wasDisconnected = false;
	private sessionInitializing = false;
	private unsubscribers: Array<() => void> = [];

	constructor(options: AppOptions = {}) {
		const socketUrl = options.socketUrl ?? getDefaultSocketUrl();
		this.#client = new Client(socketUrl, options.clientOptions);
		this.devices = new DevicesManager(this.#client);
	}

	get client(): Client {
		return this.#client;
	}

	activeProfile = $derived.by(() => {
		if (!this.activeProfileId) return null;
		return this.profiles.find((p) => p.id === this.activeProfileId) ?? null;
	});

	fov = $derived<{ width: number; height: number }>(this.activeProfile?.fovDimensions ?? { width: 5, height: 5 });

	gridLocked = $derived(this.status?.session?.grid_locked ?? false);

	get tileSpacingX(): number {
		return this.fov.width * (1 - this.gridConfig.overlap);
	}

	get tileSpacingY(): number {
		return this.fov.height * (1 - this.gridConfig.overlap);
	}

	get gridOffsetX(): number {
		return this.gridConfig.x_offset_um / 1000;
	}

	get gridOffsetY(): number {
		return this.gridConfig.y_offset_um / 1000;
	}

	positionToGridCell(positionMm: number, axis: 'x' | 'y'): number {
		const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
		const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
		const lowerLimit = axis === 'x' ? (this.xAxis?.lowerLimit ?? 0) : (this.yAxis?.lowerLimit ?? 0);
		return Math.floor((positionMm - lowerLimit - offset) / spacing);
	}

	gridCellToPosition(gridCell: number, axis: 'x' | 'y'): number {
		const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
		const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
		const lowerLimit = axis === 'x' ? (this.xAxis?.lowerLimit ?? 0) : (this.yAxis?.lowerLimit ?? 0);
		return lowerLimit + offset + gridCell * spacing;
	}

	moveToGridCell(row: number, col: number): void {
		if (this.stageIsMoving || !this.xAxis || !this.yAxis) return;
		const targetX = this.gridCellToPosition(col, 'x');
		const targetY = this.gridCellToPosition(row, 'y');
		this.moveXY(targetX, targetY);
	}

	moveXY(x: number, y: number): void {
		this.xAxis?.move(x);
		this.yAxis?.move(y);
	}

	moveZ(z: number): void {
		this.zAxis?.move(z);
	}

	async haltStage(): Promise<void> {
		await Promise.all([this.xAxis?.halt(), this.yAxis?.halt(), this.zAxis?.halt()]);
	}

	#getSelectedTile(): Tile {
		const [row, col] = this.#selectedTilePos;
		const tile = this.tiles.find((t) => t.row === row && t.col === col);
		if (tile) return tile;

		return {
			row,
			col,
			x_um: 0,
			y_um: 0,
			w_um: this.fov.width * 1000,
			h_um: this.fov.height * 1000
		};
	}

	selectTile(row: number, col: number): void {
		this.#selectedTilePos = [row, col];
	}

	setGridOffset(xOffsetUm: number, yOffsetUm: number): void {
		this.#client.send({ topic: 'grid/set_offset', payload: { x_offset_um: xOffsetUm, y_offset_um: yOffsetUm } });
	}

	setGridOverlap(overlap: number): void {
		this.#client.send({ topic: 'grid/set_overlap', payload: { overlap } });
	}

	setTileOrder(order: TileOrder): void {
		this.#client.send({ topic: 'grid/set_tile_order', payload: { tile_order: order } });
	}

	addStacks(stacks: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): void {
		this.#client.send({
			topic: 'stacks/add',
			payload: {
				stacks: stacks.map((s) => ({
					row: s.row,
					col: s.col,
					z_start_um: s.zStartUm,
					z_end_um: s.zEndUm
				}))
			}
		});
	}

	editStacks(edits: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): void {
		this.#client.send({
			topic: 'stacks/edit',
			payload: {
				edits: edits.map((e) => ({
					row: e.row,
					col: e.col,
					z_start_um: e.zStartUm,
					z_end_um: e.zEndUm
				}))
			}
		});
	}

	removeStacks(positions: Array<{ row: number; col: number }>): void {
		this.#client.send({ topic: 'stacks/remove', payload: { positions } });
	}

	async initialize(): Promise<void> {
		this.connectionError = null;
		this.subscribeToTopics();

		try {
			await this.#client.connect();
			this.#client.requestStatus();
		} catch (error) {
			this.connectionError = error instanceof Error ? error.message : 'Failed to connect';
			throw error;
		}
	}

	private subscribeToTopics(): void {
		const unsubStatus = this.#client.on('status', (status) => {
			this.handleStatusUpdate(status);
		});

		const unsubProfile = this.#client.on('profile/changed', (payload) => {
			console.debug('[App] Profile changed:', payload.profile_id);
			this.requestWaveforms();
		});

		const unsubWaveforms = this.#client.on('daq/waveforms', (waveforms) => {
			this.handleWaveforms(waveforms);
		});

		const unsubLogs = this.#client.on('log/message', (log) => {
			this.handleLog(log);
		});

		const unsubError = this.#client.on('error', (payload) => {
			console.error('[App] Error from backend:', payload.error);
			this.handleLog({
				level: 'error',
				message: payload.error,
				logger: 'backend',
				timestamp: new SvelteDate().toISOString()
			});
		});

		const unsubConnection = this.#client.onConnectionChange((connected) => {
			const wasDisconnected = this.wasDisconnected;
			this.wasDisconnected = !connected;

			if (!connected && this.status !== null) {
				this.connectionError = 'Connection lost. Attempting to reconnect...';
			} else if (connected && wasDisconnected) {
				this.handleReconnection();
			}
		});

		this.unsubscribers.push(unsubStatus, unsubProfile, unsubWaveforms, unsubLogs, unsubError, unsubConnection);
	}

	private async handleStatusUpdate(status: AppStatus): Promise<void> {
		const previousProfileId = this.activeProfileId;
		this.status = status;

		switch (status.phase) {
			case 'idle': {
				if (this.previewState || this.config) {
					this.previewState?.shutdown();
					this.previewState = null;
					this.config = null;
					this.colormapCatalog = [];
					this.profiles = [];
				}
				this.sessionInitializing = false;
				break;
			}

			case 'ready': {
				if (!this.previewState && !this.sessionInitializing) {
					this.sessionInitializing = true;
					try {
						await this.initializeSession();
					} finally {
						this.sessionInitializing = false;
					}
				}

				const currentProfileId = status.session?.active_profile_id ?? null;
				if (currentProfileId && currentProfileId !== previousProfileId) {
					this.requestWaveforms();
				}
				break;
			}
		}
	}

	private async initializeSession(): Promise<void> {
		await this.fetchConfig();
		await this.devices.initialize();
		this.#client.requestWaveforms();

		fetchColormapCatalog(this.#client.baseUrl)
			.then((catalog) => {
				this.colormapCatalog = catalog;
			})
			.catch((e) => console.warn('[App] Failed to fetch colormap catalog:', e));

		if (this.config) {
			this.previewState = new PreviewState(this.client, {
				channels: this.config.channels,
				profiles: this.config.profiles
			});

			const stage = this.config.stage;
			if (stage?.x) this.xAxis = new Axis(this, stage.x);
			if (stage?.y) this.yAxis = new Axis(this, stage.y);
			if (stage?.z) this.zAxis = new Axis(this, stage.z);
		}
	}

	private handleReconnection(): void {
		console.debug('[App] Reconnected - refetching data');
		this.connectionError = null;
		this.#client.requestStatus();
	}

	private handleWaveforms(waveforms: DaqWaveforms): void {
		if (this.activeProfile) {
			this.activeProfile.waveforms = waveforms;
			this.activeProfile.waveformsLoading = false;
			console.debug('[App] Received waveforms for active profile:', Object.keys(waveforms));
		}
	}

	private handleLog(log: LogMessage): void {
		this.logs = [...this.logs, log].slice(-MAX_LOGS);
	}

	async fetchConfig(): Promise<void> {
		if (!this.hasSession) {
			console.warn('[App] Cannot fetch config: no active session');
			return;
		}

		this.configLoading = true;
		this.configError = null;

		try {
			const response = await fetch(`${this.client.baseUrl}/config`);
			if (!response.ok) {
				throw new Error(`Failed to fetch config: ${response.statusText}`);
			}

			this.config = await response.json();
			this.buildProfiles();
		} catch (e) {
			this.configError = e instanceof Error ? e.message : 'Unknown error';
			console.error('[App] Failed to fetch config:', e);
		} finally {
			this.configLoading = false;
		}
	}

	private buildProfiles(): void {
		if (!this.config) {
			this.profiles = [];
			return;
		}

		this.profiles = Object.entries(this.config.profiles).map(([profileId, profileConfig]: [string, ProfileConfig]) => {
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

	async activateProfile(profileId: string): Promise<void> {
		if (!browser || !profileId) return;
		if (!this.hasSession) {
			console.warn('[App] Cannot activate profile: no active session');
			return;
		}
		if (profileId === this.activeProfileId) return;

		this.error = null;
		this.isMutating = true;

		const newProfile = this.profiles.find((p) => p.id === profileId);
		if (newProfile) {
			newProfile.waveformsLoading = true;
		}

		try {
			const response = await fetch(`${this.client.baseUrl}/profiles/active`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ profile_id: profileId })
			});

			if (!response.ok) {
				throw new Error(response.statusText);
			}
		} catch (error) {
			console.error('[App] Failed to activate profile:', error);
			if (newProfile) {
				newProfile.waveformsLoading = false;
			}
			if (error instanceof Error) {
				this.error = error.message || 'Failed to activate profile';
			}
			throw error;
		} finally {
			this.isMutating = false;
		}
	}

	requestWaveforms(): void {
		if (this.activeProfile) {
			this.activeProfile.waveformsLoading = true;
			this.#client.requestWaveforms();
		}
	}

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

			const response = await fetch(`${this.client.baseUrl}/session/create`, {
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
			const response = await fetch(`${this.client.baseUrl}/session/resume`, {
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

	async fetchMetadataTargets(): Promise<Record<string, string>> {
		try {
			const response = await fetch(`${this.client.baseUrl}/metadata/targets`);
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
				`${this.client.baseUrl}/metadata/schema?target=${encodeURIComponent(target)}`
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

	async closeSession(): Promise<void> {
		if (!browser) return;
		if (!this.hasSession) {
			console.warn('[App] No active session to close');
			return;
		}

		this.error = null;

		try {
			const response = await fetch(`${this.client.baseUrl}/session`, {
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

	async fetchSessions(rootName: string): Promise<SessionDirectory[]> {
		try {
			const response = await fetch(`${this.client.baseUrl}/roots/${encodeURIComponent(rootName)}/sessions`);
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

	async retryConnection(): Promise<void> {
		this.connectionError = null;
		this.status = null;
		try {
			await this.#client.connect();
			this.#client.requestStatus();
		} catch (error) {
			this.connectionError = error instanceof Error ? error.message : 'Failed to connect';
		}
	}

	clearLogs(): void {
		this.logs = [];
	}

	destroy(): void {
		if (this.previewState) {
			this.previewState.shutdown();
			this.previewState = null;
		}
		this.unsubscribers.forEach((unsub) => unsub());
		this.unsubscribers = [];
		this.devices.destroy();
		this.#client.destroy();
	}
}
