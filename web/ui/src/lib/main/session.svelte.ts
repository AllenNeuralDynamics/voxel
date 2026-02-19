import type { Client, DaqWaveforms } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type { AppStatus, GridConfig, Tile, Stack, LayerVisibility, TileOrder, VoxelRigConfig, ProfileConfig, ChannelConfig } from './types';
import { PreviewState } from './preview.svelte';
import { Profile, type ProfileContext } from './profile.svelte';
import { Axis } from './axis.svelte';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

export interface SessionInit {
	client: Client;
	config: VoxelRigConfig;
	status: AppStatus;
}

export class Session implements ProfileContext {
	readonly client!: Client;
	readonly config!: VoxelRigConfig;
	readonly devices!: DevicesManager;
	readonly previewState!: PreviewState;
	readonly xAxis!: Axis;
	readonly yAxis!: Axis;
	readonly zAxis!: Axis;

	profiles = $state<Profile[]>([]);

	#appStatus = $state<AppStatus>();

	activeProfileId = $derived<string | null>(this.#appStatus?.session?.active_profile_id ?? null);
	gridConfig = $derived<GridConfig>(
		this.#appStatus?.session?.grid_config ?? {
			x_offset_um: 0,
			y_offset_um: 0,
			overlap: 0.1,
			z_step_um: 2.0,
			default_z_start_um: 0,
			default_z_end_um: 100
		}
	);
	tiles = $derived<Tile[]>(this.#appStatus?.session?.tiles ?? []);
	stacks = $derived<Stack[]>(this.#appStatus?.session?.stacks ?? []);
	tileOrder = $derived<TileOrder>(this.#appStatus?.session?.tile_order ?? 'snake_row');
	gridLocked = $derived(this.#appStatus?.session?.grid_locked ?? false);

	activeProfile = $derived.by(() => {
		if (!this.activeProfileId) return null;
		return this.profiles.find((p) => p.id === this.activeProfileId) ?? null;
	});

	fov = $derived<{ width: number; height: number }>(this.activeProfile?.fovDimensions ?? { width: 5, height: 5 });

	stageWidth = $derived(this.xAxis.range);
	stageHeight = $derived(this.yAxis.range);
	stageDepth = $derived(this.zAxis.range);
	stageIsMoving = $derived(this.xAxis.isMoving || this.yAxis.isMoving || this.zAxis.isMoving);
	stageConnected = $derived(this.xAxis.isConnected && this.yAxis.isConnected && this.zAxis.isConnected);

	isMutating = $state(false);
	error = $state<string | null>(null);

	#selection = new SvelteMap<number, SvelteSet<number>>([[0, new SvelteSet([0])]]);
	selectedTiles = $derived<Tile[]>(this.#getSelectedTiles());
	layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true });

	constructor(init: SessionInit) {
		this.client = init.client;
		this.config = init.config;
		this.#appStatus = init.status;

		this.devices = new DevicesManager(init.client);
		this.previewState = new PreviewState(init.client, {
			channels: init.config.channels,
			profiles: init.config.profiles
		});

		this.xAxis = new Axis(this.devices, init.config.stage.x);
		this.yAxis = new Axis(this.devices, init.config.stage.y);
		this.zAxis = new Axis(this.devices, init.config.stage.z);

		this.#buildProfiles();
	}

	async initialize(): Promise<void> {
		await this.devices.initialize();
		this.client.requestWaveforms();
	}

	destroy(): void {
		this.previewState.shutdown();
		this.devices.destroy();
	}

	updateStatus(status: AppStatus): void {
		const previousProfileId = this.activeProfileId;
		this.#appStatus = status;

		const currentProfileId = status.session?.active_profile_id ?? null;
		if (currentProfileId && currentProfileId !== previousProfileId) {
			this.requestWaveforms();
		}
	}

	handleWaveforms(waveforms: DaqWaveforms): void {
		if (this.activeProfile) {
			this.activeProfile.waveforms = waveforms;
			this.activeProfile.waveformsLoading = false;
			console.debug('[Session] Received waveforms for active profile:', Object.keys(waveforms));
		}
	}

	requestWaveforms(): void {
		if (this.activeProfile) {
			this.activeProfile.waveformsLoading = true;
			this.client.requestWaveforms();
		}
	}

	async activateProfile(profileId: string): Promise<void> {
		if (!profileId) return;
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
			console.error('[Session] Failed to activate profile:', error);
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

	// --- Movement ---

	moveXY(x: number, y: number): void {
		this.xAxis.move(x);
		this.yAxis.move(y);
	}

	moveZ(z: number): void {
		this.zAxis.move(z);
	}

	async haltStage(): Promise<void> {
		await Promise.all([this.xAxis.halt(), this.yAxis.halt(), this.zAxis.halt()]);
	}

	moveToGridCell(row: number, col: number): void {
		if (this.stageIsMoving) return;
		const targetX = this.gridCellToPosition(col, 'x');
		const targetY = this.gridCellToPosition(row, 'y');
		this.moveXY(targetX, targetY);
	}

	// --- Geometry ---

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
		const lowerLimit = axis === 'x' ? this.xAxis.lowerLimit : this.yAxis.lowerLimit;
		return Math.floor((positionMm - lowerLimit - offset) / spacing);
	}

	gridCellToPosition(gridCell: number, axis: 'x' | 'y'): number {
		const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
		const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
		const lowerLimit = axis === 'x' ? this.xAxis.lowerLimit : this.yAxis.lowerLimit;
		return lowerLimit + offset + gridCell * spacing;
	}

	// --- Private ---

	#buildProfiles(): void {
		this.profiles = Object.entries(this.config.profiles).map(([profileId, profileConfig]: [string, ProfileConfig]) => {
			const channels: Record<string, ChannelConfig> = {};
			for (const channelId of profileConfig.channels) {
				const channelConfig = this.config.channels[channelId];
				if (channelConfig) {
					channels[channelId] = channelConfig;
				}
			}
			return new Profile(profileId, profileConfig, channels, this);
		});
	}
}
