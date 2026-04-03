import { toast } from 'svelte-sonner';
import type { Client, DaqWaveformsResponse } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import { sanitizeString } from '$lib/utils';
import type {
  AppStatus,
  AcquisitionConfig,
  GridConfig,
  Interleaving,
  SessionInfo,
  StorageConfig,
  Tile,
  Stack,
  StackStatus,
  TileOrder,
  RigMode,
  VoxelRigConfig
} from './types';

import { PreviewState, compositeFullFrames } from './preview.svelte';
import { Stage } from './axis.svelte';
import { Laser } from './laser.svelte';
import { Camera } from './camera.svelte';
import { SnapshotStore, type SnapshotChannel } from './snapshots.svelte';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { type AlignEdge, computeAlignedOffset } from './grid';

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

  acq = $derived<AcquisitionConfig>(
    this.#appStatus?.session?.acq ?? {
      profile_order: [],
      tile_order: 'row_wise',
      interleaving: 'position_first'
    }
  );
  storage = $derived<StorageConfig>(
    this.#appStatus?.session?.storage ?? {
      max_level: 3,
      compression: 'blosc.lz4',
      batch_z_shards: 1,
      target_shard_gb: 1.0
    }
  );
  acquisitionProfileIds = $derived<string[]>(this.acq.profile_order);
  gridConfig = $derived<GridConfig | null>(
    this.config.profiles[this.#appStatus?.session?.active_profile_id ?? '']?.grid ?? null
  );
  tiles = $derived<Tile[]>(this.#appStatus?.session?.tiles ?? []);
  stacks = $derived<Stack[]>(this.#appStatus?.session?.stacks ?? []);
  activeStacks = $derived<Stack[]>(this.stacks.filter((s) => s.profile_id === this.activeProfileId));
  tileOrder = $derived<TileOrder>(this.acq.tile_order);
  interleaving = $derived<Interleaving>(this.acq.interleaving);
  mode = $derived<RigMode>(this.#appStatus?.session?.mode ?? 'idle');
  metadata = $derived<Record<string, unknown>>(this.#appStatus?.session?.metadata ?? {});

  fov = $derived.by(() => {
    const fov = this.#appStatus?.session?.fov;
    if (!fov) return { width: 5000, height: 5000 };
    return { width: fov[0], height: fov[1] };
  });

  lasers: Record<string, Laser>;
  cameras: Record<string, Camera>;

  // ── Profile state ───────────────────────────────────────

  activeProfileId = $derived<string | null>(this.#appStatus?.session?.active_profile_id ?? null);
  appliedWaveforms = $state<DaqWaveformsResponse | null>(null);
  isSwitchingProfile = $state(false);

  // ── Snapshots ────────────────────────────────────────────

  readonly snaps = new SnapshotStore();

  // ── Grid lock ────────────────────────────────────────────

  gridForceUnlocked = $state(false);
  gridEditable = $derived(this.activeStacks.length === 0 || this.gridForceUnlocked);

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
      }),
      init.client.on('profile/roi_saved', (payload) => {
        const profile = this.config.profiles[payload.profile_id];
        if (profile) {
          if (!profile.rois) profile.rois = {};
          profile.rois[payload.camera_id] = payload.roi;
          toast.success(`Saved ROI for ${payload.camera_id}`);
        }
      }),
      init.client.on('profile/roi_applied', (payload) => {
        toast.success(`Applied saved ROI to ${payload.camera_id}`);
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

  // --- Camera ROI ---

  async saveProfileRoi(cameraId: string): Promise<void> {
    try {
      await this.#rest('POST', '/rig/profile/save-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save ROI');
    }
  }

  async applyProfileRoi(cameraId: string): Promise<void> {
    try {
      await this.#rest('POST', '/rig/profile/apply-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply ROI');
    }
  }

  // --- Snapshots ---

  static readonly SNAPSHOT_THUMB_SIZE = 256;

  async snap(): Promise<void> {
    const channels = this.preview.channels;
    const hasFrames = channels.some((ch) => ch.visible && ch.frame);
    if (!hasFrames) {
      toast.error('No preview frames available');
      return;
    }

    const w = this.preview.previewWidth;
    const h = this.preview.previewHeight;
    if (!w || !h) return;

    // Composite full-res frame
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    compositeFullFrames(ctx, canvas, channels);

    // Generate blob (full-res JPEG)
    const blob = await new Promise<Blob>((resolve) => {
      canvas.toBlob((b) => resolve(b!), 'image/jpeg', 0.85);
    });

    // Generate thumbnail
    const thumbW = Session.SNAPSHOT_THUMB_SIZE;
    const thumbH = Math.round((h / w) * thumbW);
    canvas.width = thumbW;
    canvas.height = thumbH;
    ctx.clearRect(0, 0, thumbW, thumbH);
    compositeFullFrames(ctx, canvas, channels);
    const thumbnail = canvas.toDataURL('image/jpeg', 0.6);

    // Stage position and FOV are already in µm
    const stageX = this.stage.x?.position ?? 0;
    const stageY = this.stage.y?.position ?? 0;
    const stageZ = this.stage.z?.position ?? 0;
    const fovW = this.fov.width;
    const fovH = this.fov.height;

    // Active profile at capture time
    const profileId = this.activeProfileId ?? '';
    const profile = this.config.profiles[profileId];
    const profileLabel = profile?.label ?? sanitizeString(profileId);

    // Capture channel metadata
    const snapChannels: Record<string, SnapshotChannel> = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.name) continue;
      const chConfig = this.config.channels[ch.name];
      const entry: SnapshotChannel = {
        label: ch.label ?? ch.name,
        colormap: ch.colormap,
        levelsMin: ch.levelsMin,
        levelsMax: ch.levelsMax
      };
      if (chConfig?.detection) {
        const cam = this.cameras[chConfig.detection];
        if (cam) {
          entry.detection = {
            deviceId: chConfig.detection,
            exposureTime: cam.exposureTimeMs ?? undefined,
            resolution: cam.frameSizePx ?? undefined,
            binning: cam.binning ?? undefined,
            pixelFormat: cam.pixelFormat ?? undefined
          };
        }
      }
      if (chConfig?.illumination) {
        const laser = this.lasers[chConfig.illumination];
        if (laser) {
          entry.illumination = {
            deviceId: chConfig.illumination,
            powerSetpoint: laser.powerSetpoint ?? undefined,
            power: laser.powerMw ?? undefined
          };
        }
      }
      snapChannels[ch.name] = entry;
    }

    this.snaps.add({
      profileId,
      profileLabel,
      stageX,
      stageY,
      stageZ,
      fovW,
      fovH,
      channels: snapChannels,
      timestamp: Date.now(),
      blob,
      thumbnail
    });
  }

  // --- Grid ---

  async setGridOffset(xOffsetUm: number, yOffsetUm: number): Promise<void> {
    try {
      await this.#rest('PATCH', '/acq/grid', {
        x_offset: xOffsetUm,
        y_offset: yOffsetUm,
        force: this.gridForceUnlocked
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set grid offset');
    }
  }

  alignGrid(edge: AlignEdge, position?: { x: number; y: number }): void {
    if (!this.gridConfig || !this.stage.x || !this.stage.y) return;
    const stagePos = position ?? { x: this.stage.x.position, y: this.stage.y.position };
    const { xOffsetUm, yOffsetUm } = computeAlignedOffset(
      edge,
      stagePos,
      { x: this.stage.x.lowerLimit, y: this.stage.y.lowerLimit },
      { x: this.gridOffsetX, y: this.gridOffsetY },
      { x: this.tileSpacingX, y: this.tileSpacingY }
    );
    this.setGridOffset(xOffsetUm, yOffsetUm);
  }

  async setGridOverlap(overlapX: number, overlapY: number): Promise<void> {
    try {
      await this.#rest('PATCH', '/acq/grid', {
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
      await this.#rest('PATCH', '/acq/grid', {
        default_z_start: defaultZStartUm,
        default_z_end: defaultZEndUm
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set Z range');
    }
  }

  async setTileOrder(order: TileOrder): Promise<void> {
    try {
      await this.#rest('PUT', '/acq/tile-order', { tile_order: order });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set tile order');
    }
  }

  // --- Acquisition Plan ---

  async setInterleaving(interleaving: Interleaving): Promise<void> {
    try {
      await this.#rest('PUT', '/acq/interleaving', { interleaving });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set interleaving');
    }
  }

  async updateStorage(settings: Record<string, unknown>): Promise<void> {
    try {
      await this.#rest('PATCH', '/acq/storage', settings);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update storage settings');
    }
  }

  async startAcquisition(tileId?: string): Promise<void> {
    try {
      const path = tileId ? `/acq/start/${tileId}` : '/acq/start';
      await this.#rest('POST', path);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to start acquisition');
    }
  }

  async stopAcquisition(): Promise<void> {
    try {
      await this.#rest('POST', '/acq/stop');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to stop acquisition');
    }
  }

  async reorderProfiles(profileIds: string[]): Promise<void> {
    try {
      await this.#rest('PUT', '/acq/profiles/reorder', { profile_ids: profileIds });
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
      await this.#rest('POST', '/acq/stacks', {
        stacks: stacks.map((s) => ({
          row: s.row,
          col: s.col,
          z_start: s.zStartUm,
          z_end: s.zEndUm
        }))
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to add stacks');
    }
  }

  async editStacks(edits: Array<{ row: number; col: number; zStartUm: number; zEndUm: number }>): Promise<void> {
    try {
      await this.#rest('PATCH', '/acq/stacks', {
        edits: edits.map((e) => ({
          row: e.row,
          col: e.col,
          z_start: e.zStartUm,
          z_end: e.zEndUm
        }))
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to edit stacks');
    }
  }

  async removeStacks(positions: Array<{ row: number; col: number }>): Promise<void> {
    this.gridForceUnlocked = false;
    try {
      await this.#rest('DELETE', '/acq/stacks', { positions });
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
    return this.gridConfig?.x_offset ?? 0;
  }

  get gridOffsetY(): number {
    return this.gridConfig?.y_offset ?? 0;
  }

  positionToGridCell(position: number, axis: 'x' | 'y'): number {
    const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
    const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
    const lowerLimit = axis === 'x' ? this.stage.x.lowerLimit : this.stage.y.lowerLimit;
    return Math.floor((position - lowerLimit - offset) / spacing);
  }

  gridCellToPosition(gridCell: number, axis: 'x' | 'y'): number {
    const offset = axis === 'x' ? this.gridOffsetX : this.gridOffsetY;
    const spacing = axis === 'x' ? this.tileSpacingX : this.tileSpacingY;
    const lowerLimit = axis === 'x' ? this.stage.x.lowerLimit : this.stage.y.lowerLimit;
    return lowerLimit + offset + gridCell * spacing;
  }
}
