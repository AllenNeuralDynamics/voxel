import { toast } from 'svelte-sonner';
import type { Client, DaqWaveformsResponse } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type {
	AppStatus,
	AcquisitionPlan,
	GridConfig,
	Tile,
	Stack,
	StackStatus,
	LayerVisibility,
	TileOrder,
	RigMode,
	VoxelRigConfig
} from './types';

import { PreviewState } from './preview.svelte';
import { Workflow } from './workflow.svelte';
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
	readonly workflow!: Workflow;
	readonly stage!: Stage;

	#appStatus = $state<AppStatus>();

	plan = $derived<AcquisitionPlan>(this.#appStatus?.session?.plan ?? { grid_configs: {}, stacks: [] });
	acquisitionProfileIds = $derived<string[]>(Object.keys(this.plan.grid_configs));
	gridConfig = $derived<GridConfig | null>(this.#appStatus?.session?.grid_config ?? null);
	tiles = $derived<Tile[]>(this.#appStatus?.session?.tiles ?? []);
	stacks = $derived<Stack[]>(this.#appStatus?.session?.stacks ?? []);
	tileOrder = $derived<TileOrder>(this.#appStatus?.session?.tile_order ?? 'snake_row');
	gridLocked = $derived(this.#appStatus?.session?.grid_locked ?? false);
	mode = $derived<RigMode>(this.#appStatus?.session?.mode ?? 'idle');
	sessionDir = $derived<string>(this.#appStatus?.session?.session_dir ?? '');

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

	// ── Internal ────────────────────────────────────────────

	#unsubscribers: Array<() => void> = [];
	#selection = new SvelteMap<number, SvelteSet<number>>([[0, new SvelteSet([0])]]);
	selectedTiles = $derived<Tile[]>(this.#getSelectedTiles());
	layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true });

	constructor(init: SessionInit) {
		this.client = init.client;
		this.config = init.config;
		this.#appStatus = init.status;

		this.devices = new DevicesManager(init.client);
		this.workflow = new Workflow(init.client);
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
				if (payload.devices) {
					toast.success(`Saved props for ${payload.devices.length} device(s)`);
				} else if (payload.device_id) {
					toast.success(`Saved props for ${payload.device_id}`);
				}
			}),
			init.client.on('profile/props_applied', (payload) => {
				toast.success(`Applied saved props to ${payload.devices.length} device(s)`);
			})
		);
	}

	async initialize(): Promise<void> {
		await this.devices.initialize();
		this.appliedWaveforms = await this.client.fetchWaveforms();
	}

	destroy(): void {
		this.#unsubscribers.forEach((unsub) => unsub());
		this.#unsubscribers = [];
		this.workflow.destroy();
		this.preview.destroy();
		this.devices.destroy();
	}

	updateStatus(status: AppStatus): void {
		this.#appStatus = status;
	}

	// ── Profile commands ────────────────────────────────────

	async activateProfile(profileId: string): Promise<void> {
		if (!profileId || profileId === this.activeProfileId) return;

		this.isSwitchingProfile = true;

		try {
			const response = await fetch(`${this.client.baseUrl}/profiles/active`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ profile_id: profileId })
			});
			if (!response.ok) throw new Error(response.statusText);
		} catch (error) {
			console.error('[Session] Failed to activate profile:', error);
			const msg = error instanceof Error ? error.message : 'Failed to activate profile';
			toast.error(msg);
			throw error;
		} finally {
			this.isSwitchingProfile = false;
		}
	}

	saveProfileProps(deviceId: string): void {
		this.client.send({ topic: 'profile/save_props', payload: { device_id: deviceId } });
	}

	saveAllProfileProps(): void {
		this.client.send({ topic: 'profile/save_props', payload: { all: true } });
	}

	applyProfileProps(): void {
		this.client.send({ topic: 'profile/apply_props', payload: {} });
	}

	// --- Grid ---

	setGridOffset(xOffsetUm: number, yOffsetUm: number): void {
		this.client.send({ topic: 'grid/set_offset', payload: { x_offset_um: xOffsetUm, y_offset_um: yOffsetUm } });
	}

	setGridOverlap(overlap: number): void {
		this.client.send({ topic: 'grid/set_overlap', payload: { overlap } });
	}

	setTileOrder(order: TileOrder): void {
		this.client.send({ topic: 'grid/set_tile_order', payload: { tile_order: order } });
	}

	// --- Acquisition Plan ---

	addAcquisitionProfile(profileId: string): void {
		this.client.send({ topic: 'plan/add_profile', payload: { profile_id: profileId } });
	}

	removeAcquisitionProfile(profileId: string): void {
		this.client.send({ topic: 'plan/remove_profile', payload: { profile_id: profileId } });
	}

	// --- Stacks ---

	addStacks(stacks: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): void {
		this.client.send({
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
		this.client.send({
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
		this.client.send({ topic: 'stacks/remove', payload: { positions } });
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
		const stackPositions = new SvelteSet(this.stacks.map((s) => `${s.row},${s.col}`));
		this.selectTiles(this.tiles.filter((t) => stackPositions.has(`${t.row},${t.col}`)).map((t) => [t.row, t.col]));
	}

	selectWithoutStacks(): void {
		const stackPositions = new SvelteSet(this.stacks.map((s) => `${s.row},${s.col}`));
		this.selectTiles(this.tiles.filter((t) => !stackPositions.has(`${t.row},${t.col}`)).map((t) => [t.row, t.col]));
	}

	selectByStackStatus(status: StackStatus): void {
		this.selectTiles(this.stacks.filter((s) => s.status === status).map((s) => [s.row, s.col]));
	}

	getStack(row: number, col: number): Stack | undefined {
		return this.stacks.find((s) => s.row === row && s.col === col);
	}

	moveToGridCell(row: number, col: number): void {
		if (this.stage.isMoving) return;
		const targetX = this.gridCellToPosition(col, 'x');
		const targetY = this.gridCellToPosition(row, 'y');
		this.stage.moveXY(targetX, targetY);
	}

	// --- Geometry ---

	get tileSpacingX(): number {
		return this.fov.width * (1 - (this.gridConfig?.overlap ?? 0.1));
	}

	get tileSpacingY(): number {
		return this.fov.height * (1 - (this.gridConfig?.overlap ?? 0.1));
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
