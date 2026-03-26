import { toast } from 'svelte-sonner';
import type { Client, DaqWaveformsResponse } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type {
	AppStatus,
	AcquisitionPlan,
	GridConfig,
	Interleaving,
	SessionInfo,
	Tile,
	Stack,
	StackStatus,
	TileOrder,
	RigMode,
	VoxelRigConfig
} from './types';

import { PreviewState } from './preview.svelte';
import { Stage } from './axis.svelte';
import { Laser } from './laser.svelte';
import { Camera } from './camera.svelte';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

export interface SessionInit {
	client: Client;
	config: VoxelRigConfig;
	status: AppStatus;
}

export class Session {
	readonly client!: Client;
	config = $state<VoxelRigConfig>(null!);
	readonly devices!: DevicesManager;
	readonly preview!: PreviewState;
	readonly stage!: Stage;

	#appStatus = $state<AppStatus>();
	info = $state<SessionInfo>(null!);

	plan = $derived<AcquisitionPlan>(
		this.#appStatus?.session?.plan ?? {
			profile_order: [],
			tile_order: 'row_wise',
			interleaving: 'position_first',
			stacks: []
		}
	);
	acquisitionProfileIds = $derived<string[]>(this.plan.profile_order);
	gridConfig = $derived<GridConfig | null>(
		this.config.profiles[this.#appStatus?.session?.active_profile_id ?? '']?.grid ?? null
	);
	tiles = $derived<Tile[]>(this.#appStatus?.session?.tiles ?? []);
	stacks = $derived<Stack[]>(this.#appStatus?.session?.stacks ?? []);
	activeStacks = $derived<Stack[]>(this.stacks.filter((s) => s.profile_id === this.activeProfileId));
	tileOrder = $derived<TileOrder>(this.plan.tile_order);
	interleaving = $derived<Interleaving>(this.plan.interleaving);
	mode = $derived<RigMode>(this.#appStatus?.session?.mode ?? 'idle');
	metadata = $derived<Record<string, unknown>>(this.#appStatus?.session?.metadata ?? {});

	fov = $derived.by(() => {
		const fovUm = this.#appStatus?.session?.fov_um;
		if (!fovUm) return { width: 5, height: 5 };
		return {
			width: fovUm[0] / 1000,
			height: fovUm[1] / 1000
		};
	});

	lasers: Record<string, Laser>;
	cameras: Record<string, Camera>;

	// ── Profile state ───────────────────────────────────────

	activeProfileId = $derived<string | null>(this.#appStatus?.session?.active_profile_id ?? null);
	appliedWaveforms = $state<DaqWaveformsResponse | null>(null);
	isSwitchingProfile = $state(false);

	// ── Grid lock ────────────────────────────────────────────

	gridForceUnlocked = $state(false);

	// ── Internal ────────────────────────────────────────────

	#unsubscribers: Array<() => void> = [];
	#selection = new SvelteMap<number, SvelteSet<number>>([[0, new SvelteSet([0])]]);
	selectedTiles = $derived<Tile[]>(this.#getSelectedTiles());

	constructor(init: SessionInit) {
		this.client = init.client;
		this.config = init.config;
		this.#appStatus = init.status;

		this.devices = new DevicesManager(init.client);
		this.preview = new PreviewState(init.client, {
			channels: init.config.channels,
			profiles: init.config.profiles
		});
		this.stage = new Stage(this.devices, init.config.stage);

		const lasers: Record<string, Laser> = {};
		if (init.config.channels) {
			for (const channel of Object.values(init.config.channels)) {
				if (channel.illumination && !lasers[channel.illumination]) {
					lasers[channel.illumination] = new Laser(this.devices, channel.illumination);
				}
			}
		}
		this.lasers = lasers;

		const cameras: Record<string, Camera> = {};
		if (init.config.channels) {
			for (const channel of Object.values(init.config.channels)) {
				if (channel.detection && !cameras[channel.detection]) {
					cameras[channel.detection] = new Camera(this.devices, channel.detection);
				}
			}
		}
		this.cameras = cameras;

		// Profile WebSocket subscriptions
		this.#unsubscribers.push(
			init.client.on('daq/waveforms', (data) => {
				this.appliedWaveforms = data;
				// Update config with broadcasted waveform descriptors + timing
				if (data.profile_id && this.config.profiles[data.profile_id]) {
					const profile = this.config.profiles[data.profile_id];
					if (data.waveforms) profile.daq.waveforms = data.waveforms;
					if (data.timing) profile.daq.timing = data.timing;
				}
			}),
			init.client.on('profile/props_saved', (payload) => {
				let count = 0;
				for (const [profileId, devices] of Object.entries(payload)) {
					const profile = this.config.profiles[profileId];
					if (!profile) continue;
					if (!profile.props) profile.props = {};
					for (const [deviceId, props] of Object.entries(devices)) {
						profile.props[deviceId] = props;
						count++;
					}
				}
				toast.success(`Saved props for ${count} device(s)`);
			}),
			init.client.on('profile/props_applied', (payload) => {
				toast.success(`Applied saved props to ${payload.devices.length} device(s)`);
			})
		);
	}

	async initialize(): Promise<void> {
		const [info] = await Promise.all([this.client.fetchSessionInfo(), this.devices.initialize()]);
		this.info = info;
		this.appliedWaveforms = await this.client.fetchWaveforms();
	}

	destroy(): void {
		this.#unsubscribers.forEach((unsub) => unsub());
		this.#unsubscribers = [];
		this.preview.destroy();
		this.devices.destroy();
	}

	updateStatus(status: AppStatus): void {
		this.#appStatus = status;

		// Sync grid config from status into local rig config so it stays current
		const pid = status.session?.active_profile_id;
		const gc = status.session?.grid_config;
		if (pid && gc && this.config.profiles[pid]) {
			this.config.profiles[pid].grid = gc;
		}
	}

	// ── REST helpers ────────────────────────────────────────

	async #rest(method: string, path: string, body?: unknown): Promise<Response> {
		const res = await fetch(`${this.client.baseUrl}/api${path}`, {
			method,
			...(body !== undefined && {
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			})
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({ detail: res.statusText }));
			throw new Error(data.detail || res.statusText);
		}
		return res;
	}

	// ── Profile commands ────────────────────────────────────

	async activateProfile(profileId: string): Promise<void> {
		if (!profileId || profileId === this.activeProfileId) return;

		this.gridForceUnlocked = false;
		this.isSwitchingProfile = true;

		try {
			await this.#rest('POST', '/rig/profile/active', { profile_id: profileId });
		} catch (error) {
			console.error('[Session] Failed to activate profile:', error);
			const msg = error instanceof Error ? error.message : 'Failed to activate profile';
			toast.error(msg);
			throw error;
		} finally {
			this.isSwitchingProfile = false;
		}
	}

	async saveProfileProps(deviceId: string): Promise<void> {
		try {
			await this.#rest('POST', '/rig/profile/save-props', { device_id: deviceId });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to save props');
		}
	}

	async saveAllProfileProps(): Promise<void> {
		try {
			await this.#rest('POST', '/rig/profile/save-props', { all: true });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to save all props');
		}
	}

	async applyProfileProps(deviceIds?: string[]): Promise<void> {
		try {
			await this.#rest('POST', '/rig/profile/apply-props', deviceIds ? { device_ids: deviceIds } : {});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to apply props');
		}
	}

	// --- Grid ---

	async setGridOffset(xOffsetUm: number, yOffsetUm: number): Promise<void> {
		try {
			await this.#rest('PATCH', '/plan/grid', {
				x_offset_um: xOffsetUm,
				y_offset_um: yOffsetUm,
				force: this.gridForceUnlocked
			});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to set grid offset');
		}
	}

	async setGridOverlap(overlapX: number, overlapY: number): Promise<void> {
		try {
			await this.#rest('PATCH', '/plan/grid', {
				overlap_x: overlapX,
				overlap_y: overlapY,
				force: this.gridForceUnlocked
			});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to set grid overlap');
		}
	}

	async setGridZRange(defaultZStartUm: number, defaultZEndUm: number): Promise<void> {
		try {
			await this.#rest('PATCH', '/plan/grid', {
				default_z_start_um: defaultZStartUm,
				default_z_end_um: defaultZEndUm
			});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to set Z range');
		}
	}

	async setTileOrder(order: TileOrder): Promise<void> {
		try {
			await this.#rest('PUT', '/plan/tile-order', { tile_order: order });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to set tile order');
		}
	}

	// --- Acquisition Plan ---

	async setInterleaving(interleaving: Interleaving): Promise<void> {
		try {
			await this.#rest('PUT', '/plan/interleaving', { interleaving });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to set interleaving');
		}
	}

	async reorderProfiles(profileIds: string[]): Promise<void> {
		try {
			await this.#rest('PUT', '/plan/profiles/reorder', { profile_ids: profileIds });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to reorder profiles');
		}
	}

	// --- Metadata ---

	async fetchMetadataTargets(): Promise<Record<string, string>> {
		const res = await this.#rest('GET', '/session/metadata-targets');
		const data = await res.json();
		return data.targets ?? {};
	}

	async setMetadataTarget(target: string): Promise<void> {
		try {
			const res = await this.#rest('PATCH', '/session/metadata-target', { target });
			this.info = await res.json();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to change metadata schema');
			throw error;
		}
	}

	// --- Stacks ---

	async addStacks(stacks: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): Promise<void> {
		this.gridForceUnlocked = false;
		try {
			await this.#rest('POST', '/plan/stacks', {
				stacks: stacks.map((s) => ({
					row: s.row,
					col: s.col,
					z_start_um: s.zStartUm,
					z_end_um: s.zEndUm
				}))
			});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to add stacks');
		}
	}

	async editStacks(edits: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): Promise<void> {
		try {
			await this.#rest('PATCH', '/plan/stacks', {
				edits: edits.map((e) => ({
					row: e.row,
					col: e.col,
					z_start_um: e.zStartUm,
					z_end_um: e.zEndUm
				}))
			});
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to edit stacks');
		}
	}

	async removeStacks(positions: Array<{ row: number; col: number }>): Promise<void> {
		this.gridForceUnlocked = false;
		try {
			await this.#rest('DELETE', '/plan/stacks', { positions });
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to remove stacks');
		}
	}

	// --- Selection ---

	#getSelectedTiles(): Tile[] {
		const result: Tile[] = [];
		for (const [row, cols] of this.#selection) {
			for (const col of cols) {
				const tile = this.tiles.find((t) => t.row === row && t.col === col);
				if (tile) result.push(tile);
			}
		}
		return result;
	}

	isTileSelected(row: number, col: number): boolean {
		return this.#selection.get(row)?.has(col) ?? false;
	}

	selectTiles(positions: [number, number][]): void {
		this.#selection.clear();
		for (const [row, col] of positions) {
			const cols = this.#selection.get(row);
			if (cols) cols.add(col);
			else this.#selection.set(row, new SvelteSet([col]));
		}
	}

	addToSelection(positions: [number, number][]): void {
		for (const [row, col] of positions) {
			const cols = this.#selection.get(row);
			if (cols) cols.add(col);
			else this.#selection.set(row, new SvelteSet([col]));
		}
	}

	removeFromSelection(positions: [number, number][]): void {
		for (const [row, col] of positions) {
			const cols = this.#selection.get(row);
			if (!cols) continue;
			cols.delete(col);
			if (cols.size === 0) this.#selection.delete(row);
		}
	}

	clearSelection(): void {
		this.#selection.clear();
	}

	selectAll(): void {
		this.selectTiles(this.tiles.map((t) => [t.row, t.col]));
	}

	invertSelection(): void {
		const inverted: [number, number][] = [];
		for (const t of this.tiles) {
			if (!this.isTileSelected(t.row, t.col)) inverted.push([t.row, t.col]);
		}
		this.selectTiles(inverted);
	}

	selectRow(row: number): void {
		this.selectTiles(this.tiles.filter((t) => t.row === row).map((t) => [t.row, t.col]));
	}

	selectColumn(col: number): void {
		this.selectTiles(this.tiles.filter((t) => t.col === col).map((t) => [t.row, t.col]));
	}

	selectWithStacks(): void {
		const stackPositions = new SvelteSet(this.activeStacks.map((s) => `${s.row},${s.col}`));
		this.selectTiles(this.tiles.filter((t) => stackPositions.has(`${t.row},${t.col}`)).map((t) => [t.row, t.col]));
	}

	selectWithoutStacks(): void {
		const stackPositions = new SvelteSet(this.activeStacks.map((s) => `${s.row},${s.col}`));
		this.selectTiles(this.tiles.filter((t) => !stackPositions.has(`${t.row},${t.col}`)).map((t) => [t.row, t.col]));
	}

	selectByStackStatus(status: StackStatus): void {
		this.selectTiles(this.activeStacks.filter((s) => s.status === status).map((s) => [s.row, s.col]));
	}

	getStack(row: number, col: number, profileId?: string | null): Stack | undefined {
		const pid = profileId ?? this.activeProfileId;
		return this.stacks.find((s) => s.row === row && s.col === col && s.profile_id === pid);
	}

	moveToGridCell(row: number, col: number): void {
		if (this.stage.isMoving) return;
		const targetX = this.gridCellToPosition(col, 'x');
		const targetY = this.gridCellToPosition(row, 'y');
		this.stage.moveXY(targetX, targetY);
	}

	// --- Geometry ---

	get tileSpacingX(): number {
		return this.fov.width * (1 - (this.gridConfig?.overlap_x ?? 0.1));
	}

	get tileSpacingY(): number {
		return this.fov.height * (1 - (this.gridConfig?.overlap_y ?? 0.1));
	}

	get gridOffsetX(): number {
		return (this.gridConfig?.x_offset_um ?? 0) / 1000;
	}

	get gridOffsetY(): number {
		return (this.gridConfig?.y_offset_um ?? 0) / 1000;
	}

	positionToGridCell(positionMm: number, axis: 'x' | 'y'): number {
		const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
		const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
		const lowerLimit = axis === 'x' ? this.stage.x.lowerLimit : this.stage.y.lowerLimit;
		return Math.floor((positionMm - lowerLimit - offset) / spacing);
	}

	gridCellToPosition(gridCell: number, axis: 'x' | 'y'): number {
		const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
		const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
		const lowerLimit = axis === 'x' ? this.stage.x.lowerLimit : this.stage.y.lowerLimit;
		return lowerLimit + offset + gridCell * spacing;
	}
}
