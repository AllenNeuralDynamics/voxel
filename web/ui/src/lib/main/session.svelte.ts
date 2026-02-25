import type { Client, DaqWaveforms } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import type { AppStatus, GridConfig, Tile, Stack, LayerVisibility, TileOrder, VoxelRigConfig, ProfileConfig, ChannelConfig, WorkflowStepConfig } from './types';
import { parseVec2D } from './types';
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
	readonly config!: VoxelRigConfig;
	readonly devices!: DevicesManager;
	readonly previewState!: PreviewState;
	readonly stage!: Stage;

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
	workflowSteps = $derived<WorkflowStepConfig[]>(this.#appStatus?.session?.workflow_steps ?? []);

	activeProfileConfig = $derived<ProfileConfig | null>(
		this.activeProfileId ? this.config.profiles[this.activeProfileId] ?? null : null
	);

	activeChannels = $derived.by(() => {
		if (!this.activeProfileId) return {};
		const profile = this.config.profiles[this.activeProfileId];
		if (!profile) return {};
		const result: Record<string, ChannelConfig> = {};
		for (const channelId of profile.channels) {
			const ch = this.config.channels[channelId];
			if (ch) result[channelId] = ch;
		}
		return result;
	});

	/** Find the first active channel where `detection` or `illumination` matches `deviceId`. */
	getChannelFor(deviceId: string): { id: string; config: ChannelConfig } | undefined {
		for (const [id, config] of Object.entries(this.activeChannels)) {
			if (config.detection === deviceId || config.illumination === deviceId) {
				return { id, config };
			}
		}
		return undefined;
	}

	fov = $derived.by(() => {
		if (!this.activeProfileId) return { width: 5, height: 5 };
		const profile = this.config.profiles[this.activeProfileId];
		if (!profile?.channels?.length) return { width: 5, height: 5 };
		const firstChannelId = profile.channels[0];
		const cameraId = this.config.channels[firstChannelId]?.detection;
		if (!cameraId) return { width: 5, height: 5 };
		const frameSizePx = parseVec2D(this.devices.getPropertyValue(cameraId, 'frame_size_px'));
		const pixelSizeUm = parseVec2D(this.devices.getPropertyValue(cameraId, 'pixel_size_um'));
		const magnification = this.config.detection?.[cameraId]?.magnification ?? 1.0;
		if (!frameSizePx || !pixelSizeUm) return { width: 5, height: 5 };
		return {
			width: (frameSizePx.x * pixelSizeUm.x) / (1000 * magnification),
			height: (frameSizePx.y * pixelSizeUm.y) / (1000 * magnification)
		};
	});

	waveforms = $state<DaqWaveforms | null>(null);
	waveformsLoading = $state(false);

	lasers: Record<string, Laser>;
	cameras: Record<string, Camera>;

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
		this.waveforms = waveforms;
		this.waveformsLoading = false;
	}

	requestWaveforms(): void {
		this.waveformsLoading = true;
		this.client.requestWaveforms();
	}

	async activateProfile(profileId: string): Promise<void> {
		if (!profileId) return;
		if (profileId === this.activeProfileId) return;

		this.error = null;
		this.isMutating = true;
		this.waveformsLoading = true;

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
			this.waveformsLoading = false;
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

	// --- Workflow ---

	workflowNext(): void {
		this.client.send({ topic: 'workflow/next' });
	}

	workflowReopen(stepId: string): void {
		this.client.send({ topic: 'workflow/reopen', payload: { step_id: stepId } });
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

	moveToGridCell(row: number, col: number): void {
		if (this.stage.isMoving) return;
		const targetX = this.gridCellToPosition(col, 'x');
		const targetY = this.gridCellToPosition(row, 'y');
		this.stage.moveXY(targetX, targetY);
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
