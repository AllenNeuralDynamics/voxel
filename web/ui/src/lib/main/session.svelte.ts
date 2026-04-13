import { toast } from 'svelte-sonner';
import type { Client, DaqWaveformsResponse } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import { sanitizeString, UndoStack } from '$lib/utils';
import type {
  AppStatusUpdate,
  AcquisitionConfig,
  GridConfig,
  SessionDetails,
  Tile,
  Stack,
  StackStatus,
  StackOrder,
  RigMode,
  VoxelRigConfig
} from './types';

import { PreviewState, compositeFullFrames } from './preview.svelte';
import { Stage } from './axis.svelte';
import { Laser } from './laser.svelte';
import { Camera } from './camera.svelte';
import { SnapshotStore, type SnapshotChannel } from './snapshots.svelte';
import { SvelteSet } from 'svelte/reactivity';
import { type AlignEdge, computeAlignedOffset } from './grid';

export interface SessionInit {
  client: Client;
  status: AppStatusUpdate;
}

export class Session {
  readonly client!: Client;
  readonly devices!: DevicesManager;
  preview = $state<PreviewState>(null!);
  stage = $state<Stage>(null!);

  #appStatus = $state<AppStatusUpdate>();
  details = $state<SessionDetails>(null!);
  rig_cfg = $derived<VoxelRigConfig>(this.details.config.rig!);

  acq = $derived<AcquisitionConfig>(
    this.#appStatus?.session?.acq ?? {
      profile_order: [],
      stack_order: 'snake_row',
      sort_by_profile: false,
      z_step: 1.0,
      default_z_start: 0.0,
      default_z_end: 511.0,
      store_path: './data',
      max_level: 3,
      compression: 'blosc_lz4'
    }
  );
  acquisitionProfileIds = $derived<string[]>(this.acq.profile_order);
  gridConfig = $derived<GridConfig>(
    this.#appStatus?.session?.grid ?? { x_offset: 0, y_offset: 0, overlap_x: 0.1, overlap_y: 0.1 }
  );
  stacks = $derived.by<Stack[]>(() => {
    const dict = this.#appStatus?.session?.stacks ?? {};
    const order = this.#appStatus?.session?.stack_order ?? [];
    return order.map((id) => dict[id]).filter((s): s is Stack => s !== undefined);
  });
  activeStacks = $derived<Stack[]>(this.stacks.filter((s) => s.profile_id === this.activeProfileId));
  inactiveStacks = $derived<Stack[]>(this.stacks.filter((s) => s.profile_id !== this.activeProfileId));

  tiles = $derived.by<Tile[]>(() => {
    const gc = this.gridConfig;
    const fov = this.fov;
    const sx = this.stage.x;
    const sy = this.stage.y;
    if (!sx || !sy) return [];

    const stepW = fov.width * (1 - gc.overlap_x);
    const stepH = fov.height * (1 - gc.overlap_y);
    if (stepW <= 0 || stepH <= 0) return [];

    const stageW = sx.upperLimit - sx.lowerLimit;
    const stageH = sy.upperLimit - sy.lowerLimit;

    const colMin = Math.ceil(-gc.x_offset / stepW);
    const colMax = Math.floor((stageW - gc.x_offset) / stepW) + 1;
    const rowMin = Math.ceil(-gc.y_offset / stepH);
    const rowMax = Math.floor((stageH - gc.y_offset) / stepH) + 1;

    const tiles: Tile[] = [];
    for (let row = rowMin; row < rowMax; row++) {
      for (let col = colMin; col < colMax; col++) {
        const tx = gc.x_offset + col * stepW;
        const ty = gc.y_offset + row * stepH;
        if (tx >= 0 && tx <= stageW && ty >= 0 && ty <= stageH) {
          tiles.push({ tile_id: `tile_r${row}_c${col}`, row, col, x: tx, y: ty, w: fov.width, h: fov.height });
        }
      }
    }
    return tiles;
  });
  stackOrderAlgorithm = $derived<StackOrder>(this.acq.stack_order);
  sortByProfile = $derived<boolean>(this.acq.sort_by_profile);
  mode = $derived<RigMode>(this.#appStatus?.session?.mode ?? 'idle');
  metadata = $derived<Record<string, unknown>>(this.#appStatus?.session?.metadata ?? {});

  fov = $derived.by(() => {
    const fov = this.#appStatus?.session?.fov;
    if (!fov) return { width: 5000, height: 5000 };
    return { width: fov[0], height: fov[1] };
  });

  lasers = $state<Record<string, Laser>>({});
  cameras = $state<Record<string, Camera>>({});

  // ── Profile state ───────────────────────────────────────

  activeProfileId = $derived<string | null>(this.#appStatus?.session?.active_profile_id ?? null);
  appliedWaveforms = $state<DaqWaveformsResponse | null>(null);
  isSwitchingProfile = $state(false);

  // ── Snapshots ────────────────────────────────────────────

  readonly snaps = new SnapshotStore();
  readonly undo = new UndoStack();

  // ── Internal ────────────────────────────────────────────

  #unsubscribers: Array<() => void> = [];
  #selectedStackIds = new SvelteSet<string>();
  selectedStacks = $derived<Stack[]>(this.stacks.filter((s) => this.#selectedStackIds.has(s.stack_id)));

  constructor(init: SessionInit) {
    this.client = init.client;
    this.#appStatus = init.status;
    this.devices = new DevicesManager(init.client);
  }

  async initialize(): Promise<void> {
    const [details] = await Promise.all([this.client.fetchSessionDetails(), this.devices.initialize()]);
    this.details = details;

    this.preview = new PreviewState(this.client, this.rig_cfg);
    this.stage = new Stage(this.devices, this.rig_cfg.stage);

    const lasers: Record<string, Laser> = {};
    if (this.rig_cfg.channels) {
      for (const channel of Object.values(this.rig_cfg.channels)) {
        if (channel.illumination && !lasers[channel.illumination]) {
          lasers[channel.illumination] = new Laser(this.devices, channel.illumination);
        }
      }
    }
    this.lasers = lasers;

    const cameras: Record<string, Camera> = {};
    if (this.rig_cfg.channels) {
      for (const channel of Object.values(this.rig_cfg.channels)) {
        if (channel.detection && !cameras[channel.detection]) {
          cameras[channel.detection] = new Camera(this.devices, channel.detection);
        }
      }
    }
    this.cameras = cameras;

    // Profile WebSocket subscriptions
    this.#unsubscribers.push(
      this.client.on('daq/waveforms', (data) => {
        this.appliedWaveforms = data;
        // Update config with broadcasted waveform descriptors + timing
        if (data.profile_id && this.rig_cfg.profiles[data.profile_id]) {
          const profile = this.rig_cfg.profiles[data.profile_id];
          if (data.waveforms) profile.daq.waveforms = data.waveforms;
          if (data.timing) profile.daq.timing = data.timing;
        }
      }),
      this.client.on('profile/props_saved', (payload) => {
        let count = 0;
        for (const [profileId, devices] of Object.entries(payload)) {
          const profile = this.rig_cfg.profiles[profileId];
          if (!profile) continue;
          if (!profile.props) profile.props = {};
          for (const [deviceId, props] of Object.entries(devices)) {
            profile.props[deviceId] = props;
            count++;
          }
        }
        toast.success(`Saved props for ${count} device(s)`);
      }),
      this.client.on('profile/props_applied', (payload) => {
        toast.success(`Applied saved props to ${payload.devices.length} device(s)`);
      }),
      this.client.on('profile/roi_saved', (payload) => {
        const profile = this.rig_cfg.profiles[payload.profile_id];
        if (profile) {
          if (!profile.rois) profile.rois = {};
          profile.rois[payload.camera_id] = payload.roi;
          toast.success(`Saved ROI for ${payload.camera_id}`);
        }
      }),
      this.client.on('profile/roi_applied', (payload) => {
        toast.success(`Applied saved ROI to ${payload.camera_id}`);
      })
    );

    this.appliedWaveforms = await this.client.fetchWaveforms();
  }

  destroy(): void {
    this.#unsubscribers.forEach((unsub) => unsub());
    this.#unsubscribers = [];
    this.preview.destroy();
    this.devices.destroy();
  }

  updateStatus(status: AppStatusUpdate): void {
    this.#appStatus = status;
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

    // Get dimensions from first visible channel's overview frame
    const firstFrame = channels.find((ch) => ch.visible && ch.frame)?.frame;
    if (!firstFrame) return;
    const w = firstFrame.width;
    const h = firstFrame.height;

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
    const profile = this.rig_cfg.profiles[profileId];
    const profileLabel = profile?.label ?? sanitizeString(profileId);

    // Capture channel metadata
    const snapChannels: Record<string, SnapshotChannel> = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.name) continue;
      const chConfig = this.rig_cfg.channels[ch.name];
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
            exposureTime: cam.exposure?.value ?? undefined,
            resolution: cam.frameSizePx ?? undefined,
            binning: (cam.binning?.value as number) ?? undefined,
            pixelFormat: (cam.pixelFormat?.value as string) ?? undefined
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
        y_offset: yOffsetUm
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
        overlap_y: overlapY
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

  async setStackOrder(order: StackOrder): Promise<void> {
    try {
      await this.#rest('PUT', '/acq/stack-order', { stack_order: order });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set stack order');
    }
  }

  // --- Acquisition Plan ---

  async setSortByProfile(sortByProfile: boolean): Promise<void> {
    try {
      await this.#rest('PUT', '/acq/sort-by-profile', { sort_by_profile: sortByProfile });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set sort by profile');
    }
  }

  async updateStorage(settings: Record<string, unknown>): Promise<void> {
    try {
      await this.#rest('PATCH', '/acq/storage', settings);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update storage settings');
    }
  }

  async startAcquisition(stackId?: string): Promise<void> {
    try {
      const path = stackId ? `/acq/start/${stackId}` : '/acq/start';
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
      this.details = await res.json();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to change metadata schema');
      throw error;
    }
  }

  // --- Stacks ---

  async addStacks(
    stacks: Array<{ x: number; y: number; zStartUm: number; zEndUm: number }>,
    undoTag?: string
  ): Promise<void> {
    try {
      const res = await this.#rest('POST', '/acq/stacks', {
        stacks: stacks.map((s) => ({ x: s.x, y: s.y, z_start: s.zStartUm, z_end: s.zEndUm }))
      });
      const { stacks: added } = await res.json();
      if (added?.length > 0) {
        const addedIds = added.map((s: { stack_id: string }) => s.stack_id);
        this.undo.push(
          `Add ${addedIds.length} stack${addedIds.length > 1 ? 's' : ''}`,
          () => this.removeStacks(addedIds),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to add stacks');
    }
  }

  async editStacks(
    edits: Array<{ stackId: string; x?: number; y?: number; zStartUm?: number; zEndUm?: number }>,
    undoTag?: string
  ): Promise<void> {
    // Capture old values before the API call (before WebSocket update)
    const oldValues = edits
      .map((e) => {
        const stack = this.stacks.find((s) => s.stack_id === e.stackId);
        if (!stack) return null;
        return {
          stackId: stack.stack_id,
          ...(e.x !== undefined && { x: stack.x }),
          ...(e.y !== undefined && { y: stack.y }),
          ...(e.zStartUm !== undefined && { zStartUm: stack.z_start }),
          ...(e.zEndUm !== undefined && { zEndUm: stack.z_end })
        };
      })
      .filter((v): v is NonNullable<typeof v> => v !== null);

    try {
      await this.#rest('PATCH', '/acq/stacks', {
        edits: edits.map((e) => ({
          stack_id: e.stackId,
          ...(e.x !== undefined && { x: e.x }),
          ...(e.y !== undefined && { y: e.y }),
          ...(e.zStartUm !== undefined && { z_start: e.zStartUm }),
          ...(e.zEndUm !== undefined && { z_end: e.zEndUm })
        }))
      });
      if (oldValues.length > 0) {
        this.undo.push(
          `Edit ${oldValues.length} stack${oldValues.length > 1 ? 's' : ''}`,
          () => this.editStacks(oldValues),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to edit stacks');
    }
  }

  async removeStacks(stackIds: string[], undoTag?: string): Promise<void> {
    try {
      const res = await this.#rest('DELETE', '/acq/stacks', { stack_ids: stackIds });
      const { stacks: removed } = await res.json();
      if (removed?.length > 0) {
        const readdData = removed.map((s: Stack) => ({
          x: s.x,
          y: s.y,
          zStartUm: s.z_start,
          zEndUm: s.z_end
        }));
        this.undo.push(
          `Remove ${removed.length} stack${removed.length > 1 ? 's' : ''}`,
          () => this.addStacks(readdData),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to remove stacks');
    }
  }

  // --- Stack Selection ---

  isStackSelected(stackId: string): boolean {
    return this.#selectedStackIds.has(stackId);
  }

  selectStacks(stacks: Array<{ stack_id: string }>): void {
    this.#selectedStackIds.clear();
    for (const s of stacks) {
      this.#selectedStackIds.add(s.stack_id);
    }
  }

  addStacksToSelection(stacks: Array<{ stack_id: string }>): void {
    for (const s of stacks) {
      this.#selectedStackIds.add(s.stack_id);
    }
  }

  removeStacksFromSelection(stacks: Array<{ stack_id: string }>): void {
    for (const s of stacks) {
      this.#selectedStackIds.delete(s.stack_id);
    }
  }

  clearStackSelection(): void {
    this.#selectedStackIds.clear();
  }

  selectMultipleStacks({ profileIds, status }: { profileIds?: string[]; status?: StackStatus[] } = {}): void {
    let stacks: Stack[] = this.stacks;
    if (profileIds) stacks = stacks.filter((s) => profileIds.includes(s.profile_id));
    if (status) stacks = stacks.filter((s) => status.includes(s.status));
    this.selectStacks(stacks);
  }

  /** Find a stack near the given position (within 0.1 µm tolerance). */
  getStackAtPosition(x: number, y: number, profileId?: string | null): Stack | undefined {
    const pid = profileId ?? this.activeProfileId;
    return this.stacks.find((s) => s.profile_id === pid && Math.abs(s.x - x) < 0.1 && Math.abs(s.y - y) < 0.1);
  }

  // --- Geometry ---

  get tileSpacingX(): number {
    return this.fov.width * (1 - this.gridConfig.overlap_x);
  }

  get tileSpacingY(): number {
    return this.fov.height * (1 - this.gridConfig.overlap_y);
  }

  get gridOffsetX(): number {
    return this.gridConfig.x_offset;
  }

  get gridOffsetY(): number {
    return this.gridConfig.y_offset;
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
