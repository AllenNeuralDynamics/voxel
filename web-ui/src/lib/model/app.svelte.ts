/** App-level store (`VoxelApp`) + the active-instrument store (`Instrument`) and its device handles. */
import { getContext, setContext } from 'svelte';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import { browser } from '$app/environment';
import { type DeviceRole, type DeviceRoleKind, sortByRoleOrder } from '$lib/model/role';
import { pref, sanitizeString } from '$lib/utils';
import { decodeMsgpack } from '$lib/utils/msgpack';

import { Client, type ClientOptions, errorMessage, resolveWebSocketUrl, type Unsub } from './client.svelte';
import {
  AxisHandle,
  CameraHandle,
  createDevice,
  type DeviceHandle,
  DiscreteAxisHandle,
  LaserHandle,
  SignalGeneratorHandle
} from './device.svelte';
import { Inpainter } from './inpaint.svelte';
import { SnapshotStore } from './snapshots.svelte';
import type {
  AcquisitionManifest,
  AcquisitionRequest,
  ActiveAcquisitionState,
  ChannelPatch,
  DeviceState,
  HALConfig,
  InstrumentDefaults,
  InstrumentStatus,
  JsonSchema,
  LogEntry,
  OpticalRoutingPolicy,
  PresetRecord,
  ProfilePatch,
  SensorROI,
  SessionView,
  Signals,
  StageOrientation,
  StationDiscovery,
  StationFeedView,
  StationInfo,
  StencilPatch,
  TaskPatch,
  TileOrder,
  WriterPatch
} from './types';
import { DEFAULT_STAGE_ORIENTATION } from './types';

const MAX_LOGS = 500;

/** A device's profile-derived role: its kind, palette index, and the channel that placed it there. */
export interface FilterSetting {
  wheel: DiscreteAxisHandle;
  filter: string;
}

export interface Channel {
  id: string;
  label: string;
  emission?: number;
  camera: CameraHandle;
  laser: LaserHandle;
  filters: FilterSetting[];
  auxilliary: DeviceHandle[];
}

/** How one device's live state compares to the active profile's saved settings. */
export interface DeviceDivergence {
  /** Saved rw prop values for this device (`profile.props[id]`); empty if never saved. */
  saved: Record<string, unknown>;
  /** rw prop names that need saving — diverged from the saved value, or never saved. */
  dirty: Set<string>;
  /** Camera ROI needs saving (cameras only). */
  roiDirty: boolean;
}

/** One optical-routing dimension joined across immutable topology, editable policy, and live target. */
export interface RoutingDimension {
  id: string;
  routes: string[];
  policyRoutes: string[];
  policy: OpticalRoutingPolicy;
  target?: string;
}

/** Compare two property values; treats floating-point near-equality as equal. */
function propValueDiverged(saved: unknown, current: unknown): boolean {
  if (saved === undefined || saved === null) return false;
  if (current === undefined || current === null) return false;
  if (typeof saved === 'number' && typeof current === 'number') return Math.abs(saved - current) > 1e-6;
  return saved !== current;
}

/** Whether a live ROI needs saving against the profile-saved one (never-saved counts as dirty). */
function roiDiffers(
  saved: SensorROI | undefined,
  live: SensorROI | undefined,
  sensor?: { x: number; y: number }
): boolean {
  if (!live) return false;
  if (!saved) {
    // The backend stores no ROI for a full-sensor crop (its implicit default), so an absent saved
    // ROI means "full sensor" — a live ROI is only dirty here if it's an unsaved *crop*.
    if (!sensor) return false;
    return !(live.x === 0 && live.y === 0 && live.w === sensor.x && live.h === sensor.y);
  }
  return saved.x !== live.x || saved.y !== live.y || saved.w !== live.w || saved.h !== live.h;
}

export type AlignEdge = 'top' | 'bottom' | 'left' | 'right' | 'center';

/**
 * New mosaic offset so the given edge's nearest tile center lands on `stagePos` (µm). Top/bottom snap
 * Y only, left/right snap X only, center snaps both — each tile spans one FOV, so aligning any edge on
 * an axis is the same "shift the offset to the nearest tile center" operation.
 */
function alignedOffset(
  edge: AlignEdge,
  stagePos: { x: number; y: number },
  lowerLimit: { x: number; y: number },
  offset: { x: number; y: number },
  spacing: { x: number; y: number }
): { x: number; y: number } {
  let x = offset.x;
  let y = offset.y;
  if (edge === 'left' || edge === 'right' || edge === 'center') x = snapAxis(stagePos.x - lowerLimit.x, x, spacing.x);
  if (edge === 'top' || edge === 'bottom' || edge === 'center') y = snapAxis(stagePos.y - lowerLimit.y, y, spacing.y);
  return { x, y };
}

/** Snap an offset so the nearest tile center lands on `fovCenter`. */
function snapAxis(fovCenter: number, offset: number, step: number): number {
  if (step <= 0) return offset;
  const r = (((fovCenter - offset) % step) + step) % step;
  const a = offset + r;
  const b = offset + r - step;
  return Math.abs(a - offset) <= Math.abs(b - offset) ? a : b;
}

type StageAxis = 'x' | 'y' | 'z';

/** Stage extent per axis (µm). Structurally a superset of the renderer's 2D `Bounds` (X/Y). */
export interface StageBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

/**
 * A value object over the mapped stage axes (resolved handles) + FOV + orientation: derived geometry
 * (imageable bounds, normalized position) and whole-stage move/halt commands. Constructed reactively by
 * the instrument (re-made when the mapping or FOV changes); the handles carry their own live position.
 */
/** Axis is treated as "arrived" once it's within this many µm of the commanded target. */
const TARGET_TOLERANCE_UM = 0.5;

export class Stage {
  readonly #getFov: () => [number, number] | null;

  /** Last commanded absolute position (µm), from any in-app surface. Null until something moves. */
  target = $state.raw<{ x?: number; y?: number; z?: number } | null>(null);

  constructor(
    readonly x: AxisHandle,
    readonly y: AxisHandle,
    readonly z: AxisHandle,
    getFov: () => [number, number] | null,
    /** Per-axis display sign shared with the renderers (hardcoded upstream for now). */
    readonly orientation: StageOrientation
  ) {
    this.#getFov = getFov;
  }

  /** Field of view (µm), read live so a FOV change doesn't rebuild the whole Stage. */
  get fov(): [number, number] | null {
    return this.#getFov();
  }

  axis(a: StageAxis): AxisHandle {
    return a === 'x' ? this.x : a === 'y' ? this.y : this.z;
  }

  position(a: StageAxis): number {
    return this.axis(a).position?.value ?? 0;
  }
  moving(a: StageAxis): boolean {
    return this.axis(a).isMoving?.value === true;
  }

  get anyMoving(): boolean {
    return this.moving('x') || this.moving('y') || this.moving('z');
  }

  /** True while the stage is still short of its commanded target on any axis. */
  readonly targetPending: boolean = $derived.by(() => {
    const t = this.target;
    if (!t) return false;
    return (['x', 'y', 'z'] as const).some((a) => {
      const want = t[a];
      return want != null && Math.abs(this.position(a) - want) > TARGET_TOLERANCE_UM;
    });
  });

  /** Raw [lower, upper] soft limits for an axis (µm), defaulting to [0, 1] until the limits stream in. */
  #range(a: StageAxis): [number, number] {
    const h = this.axis(a);
    return [h.lowerLimit?.value ?? 0, h.upperLimit?.value ?? 1];
  }

  /** Normalize an absolute µm value onto [0,1] for an axis (guards a zero-length range). */
  normOf(a: StageAxis, um: number): number {
    const [lo, hi] = this.#range(a);
    return hi > lo ? (um - lo) / (hi - lo) : 0;
  }

  /** Normalized [0,1] position along an axis. */
  norm(a: StageAxis): number {
    return this.normOf(a, this.position(a));
  }
  denorm(a: StageAxis, n: number): number {
    const [lo, hi] = this.#range(a);
    return lo + Math.min(1, Math.max(0, n)) * (hi - lo);
  }

  /**
   * Stage extent per axis (µm). `includeFov` expands X/Y by half a FOV on each side (the imageable
   * extent, for the top-down view); Z is unaffected. Null until the X/Y soft limits are known.
   */
  bounds(includeFov = false): StageBounds | null {
    const xl = this.x.lowerLimit?.value;
    const xu = this.x.upperLimit?.value;
    const yl = this.y.lowerLimit?.value;
    const yu = this.y.upperLimit?.value;
    if (xl == null || xu == null || yl == null || yu == null) return null;
    const [fw, fh] = includeFov ? (this.fov ?? [0, 0]) : [0, 0];
    const [zl, zu] = this.#range('z');
    return { minX: xl - fw / 2, maxX: xu + fw / 2, minY: yl - fh / 2, maxY: yu + fh / 2, minZ: zl, maxZ: zu };
  }

  /** Drive the stage to an absolute position (µm); axes omitted from `pos` are left unchanged. */
  moveTo(pos: { x?: number; y?: number; z?: number }): Promise<unknown> {
    this.target = { ...this.target, ...pos };
    const moves: Promise<unknown>[] = [];
    if (pos.x != null) moves.push(this.x.move(pos.x));
    if (pos.y != null) moves.push(this.y.move(pos.y));
    if (pos.z != null) moves.push(this.z.move(pos.z));
    return Promise.all(moves);
  }

  /** Halt all stage axes, abandoning any commanded target. */
  halt(): Promise<unknown> {
    this.target = null;
    return Promise.all([this.x.halt(), this.y.halt(), this.z.halt()]);
  }
}

export class Instrument {
  status = $state.raw<InstrumentStatus>(undefined as unknown as InstrumentStatus); // set in the constructor
  hal = $state.raw<HALConfig>(undefined as unknown as HALConfig);
  default = $state.raw<InstrumentDefaults>(undefined as unknown as InstrumentDefaults);

  readonly devices = new SvelteMap<string, DeviceHandle>();

  /** Retained manifest and current-volume progress for the active run. */
  acquisition = $state.raw<ActiveAcquisitionState | null>(null);

  readonly mode = $derived(this.status.mode);
  readonly fov = $derived(this.status.fov);
  readonly routingTargets = $derived(this.status.routing_targets);
  readonly state = $derived(this.status.state);
  readonly taskTiles = $derived(this.status.task_tiles);
  readonly imaging = $derived(this.state.imaging);
  readonly activeProfileId = $derived(this.status.active_profile_id);
  readonly activeProfile = $derived(this.activeProfileId ? this.imaging.profiles[this.activeProfileId] : undefined);

  // Devices grouped by intrinsic type — stable for the instrument's lifetime.
  readonly cameras = $derived.by(() => this.#devicesOfType(CameraHandle));
  readonly lasers = $derived.by(() => this.#devicesOfType(LaserHandle));
  readonly axes = $derived.by(() => this.#devicesOfType(AxisHandle));
  readonly discreteAxes = $derived.by(() => this.#devicesOfType(DiscreteAxisHandle));
  readonly signalGenerators = $derived.by(() => this.#devicesOfType(SignalGeneratorHandle));

  /** Optical-routing dimensions with route choices valid for both the topology and every participant. */
  readonly routingDimensions = $derived.by<RoutingDimension[]>(() => {
    const assemblies = [...Object.values(this.hal.detection), ...Object.values(this.hal.illumination)];
    return Object.entries(this.hal.optical_routing).flatMap(([id, routes]) => {
      const policy = this.state.routing[id];
      if (!policy) return [];
      const participants = assemblies.filter((assembly) => id in assembly.routing);
      const routeNames = Object.keys(routes);
      return [
        {
          id,
          routes: routeNames,
          policyRoutes: routeNames.filter((route) =>
            participants.every((assembly) => assembly.routing[id]?.includes(route) === true)
          ),
          policy,
          target: this.routingTargets[id]
        }
      ];
    });
  });

  // Discrete axes any detection path declares as a filter wheel — config-authoritative, across all profiles.
  readonly filterWheels = $derived.by<DiscreteAxisHandle[]>(() => {
    const ids = Object.values(this.hal.detection).flatMap((det) => det.filter_wheels);
    return ids
      .filter((id, i) => ids.indexOf(id) === i)
      .flatMap((id) => {
        const wheel = this.discreteAxes.get(id);
        return wheel ? [wheel] : [];
      });
  });

  /** The mapped stage: resolved axis handles + FOV + orientation. Built once at construction (all three
   *  axes are required — the constructor throws otherwise); its methods read live values off the handles. */
  readonly stage: Stage;

  #stageAxis(a: StageAxis): AxisHandle | undefined {
    const id = this.hal.stage[a];
    return id ? this.axes.get(id) : undefined;
  }

  readonly activeChannels = $derived.by<Channel[]>(() => {
    const profile = this.imaging.profiles[this.activeProfileId];
    if (!profile) return [];
    return profile.channels.flatMap((id) => {
      const ch = this.imaging.channels[id];
      const camera = this.cameras.get(ch?.detection ?? '');
      const laser = this.lasers.get(ch?.illumination ?? '');
      if (!ch || !camera || !laser) return [];
      const det = this.hal.detection[ch.detection];
      const ill = this.hal.illumination[ch.illumination];
      const filters: FilterSetting[] = (det?.filter_wheels ?? []).flatMap((wheelId) => {
        const wheel = this.discreteAxes.get(wheelId);
        return wheel ? [{ wheel, filter: ch.filters[wheelId] ?? '' }] : [];
      });
      const auxilliary = [...(det?.aux_devices ?? []), ...(ill?.aux_devices ?? [])].flatMap((auxId) => {
        const d = this.devices.get(auxId);
        return d ? [d] : [];
      });
      return [
        {
          id,
          label: ch.label || sanitizeString(id),
          emission: ch.emission ?? undefined,
          camera,
          laser,
          filters,
          auxilliary
        }
      ];
    });
  });

  // Devices grouped by contextual role — a palette index per backing device, in role order.
  // Sourced from `activeChannels` (channel devices) plus stage + sync; channel devices keep their
  // channel-derived kind (first tag wins). Emission/channel are read off `Channel`, not duplicated here.
  readonly roles = $derived.by<Map<string, DeviceRole>>(() => {
    const kinds = new SvelteMap<string, DeviceRoleKind>();
    const tag = (id: string, kind: DeviceRoleKind): void => {
      if (!kinds.has(id)) kinds.set(id, kind);
    };
    for (const ch of this.activeChannels) {
      tag(ch.camera.id, 'camera');
      tag(ch.laser.id, 'laser');
      for (const f of ch.filters) tag(f.wheel.id, 'filter');
      for (const aux of ch.auxilliary) tag(aux.id, 'aux');
    }
    for (const axisId of [this.hal.stage.x, this.hal.stage.y, this.hal.stage.z]) if (axisId) tag(axisId, 'stage');
    for (const sig of Object.values(this.activeProfile?.sync ?? {}))
      for (const devId of Object.keys(sig.waveforms)) tag(devId, 'waveform');

    const out = new SvelteMap<string, DeviceRole>();
    const counters: Record<DeviceRoleKind, number> = {
      camera: 0,
      laser: 0,
      filter: 0,
      aux: 0,
      stage: 0,
      waveform: 0,
      other: 0
    };
    for (const [id, kind] of sortByRoleOrder(kinds)) {
      if (!this.devices.has(id)) continue; // pure DAQ port labels have no backing device
      out.set(id, { kind, index: counters[kind]++ });
    }
    return out;
  });

  // Per-device divergence from the active profile, keyed by device id, over the *settable* devices:
  // channel camera/laser/aux + sync AO — never filter wheels (driven by commands) or stage. A never-saved
  // rw prop counts as dirty (so a freshly-configured device is savable). Drives save gating + propRow.
  readonly divergence = $derived.by<Map<string, DeviceDivergence>>(() => {
    const out = new SvelteMap<string, DeviceDivergence>();
    const profile = this.activeProfile;
    if (!profile) return out;
    const add = (device: DeviceHandle): void => {
      if (out.has(device.id)) return;
      const saved = profile.props[device.id] ?? {};
      const dirty = new SvelteSet<string>();
      for (const [name, prop] of device.props) {
        if (prop.access !== 'rw' || name === 'roi' || name === 'roi_grid') continue;
        if (!(name in saved) || propValueDiverged(saved[name], prop.value)) dirty.add(name);
      }
      const roiDirty =
        device instanceof CameraHandle &&
        roiDiffers(profile.rois[device.id], device.roi.value, device.sensorSizePx ?? undefined);
      out.set(device.id, { saved, dirty, roiDirty });
    };
    for (const ch of this.activeChannels) {
      add(ch.camera);
      add(ch.laser);
      for (const aux of ch.auxilliary) add(aux);
    }
    for (const sig of Object.values(profile.sync))
      for (const id of Object.keys(sig.waveforms)) {
        const device = this.devices.get(id);
        if (device) add(device);
      }
    return out;
  });

  /** Whether any settable device has unsaved changes — gates "Save Current". */
  readonly profileDirty = $derived.by<boolean>(() => {
    for (const d of this.divergence.values()) if (d.dirty.size > 0 || d.roiDirty) return true;
    return false;
  });

  /** Resolved JSON schema for the active `metadata_cls`; re-fetched from the backend when it changes. */
  metadataSchema = $state.raw<JsonSchema | null>(null);
  remoteStores = $state.raw<Record<string, import('./types').Remote>>({});

  readonly #client: Client;
  readonly #base: string;
  readonly #stationBase: string;
  readonly #onAcquisitionCreated: (manifest: AcquisitionManifest) => void;
  #schemaCls: string | null = null; // metadata_cls the schema was last fetched for

  constructor(
    client: Client,
    readonly id: string,
    readonly sessionId: string,
    readonly stationId: string,
    session: SessionView,
    readonly metadataSchemas: Record<string, string>,
    onAcquisitionCreated: (manifest: AcquisitionManifest) => void
  ) {
    this.#client = client;
    this.#stationBase = `/stations/${encodeURIComponent(stationId)}`;
    this.#base = `${this.#stationBase}/sessions/${encodeURIComponent(sessionId)}/instrument`;
    this.#onAcquisitionCreated = onAcquisitionCreated;
    this.status = this.#statusFrom(session);
    this.acquisition = session.instrument.acquisition;
    this.hal = session.instrument.config.hal;
    this.default = session.instrument.config.default;
    this.remoteStores = session.instrument.remote_stores;
    for (const [deviceId, device] of Object.entries(session.instrument.devices)) {
      const base = `${this.#base}/devices/${encodeURIComponent(deviceId)}`;
      this.devices.set(
        deviceId,
        createDevice(client, base, this.#snapshotFrom(deviceId, device), () => this.mode === 'capture')
      );
      this.devices.get(deviceId)?.replaceProperties(this.#resultsFrom(device));
    }
    const sx = this.#stageAxis('x');
    const sy = this.#stageAxis('y');
    const sz = this.#stageAxis('z');
    if (!sx || !sy || !sz) throw new Error('Instrument stage must map all three (X/Y/Z) axes');
    this.stage = new Stage(sx, sy, sz, () => this.fov, DEFAULT_STAGE_ORIENTATION);
    void this.#syncMetadataSchema();
  }

  /** Replace every runtime field from one authoritative complete Station session view. */
  applySession(session: SessionView): void {
    if (session.info.id !== this.sessionId) return;
    this.status = this.#statusFrom(session);
    this.acquisition = session.instrument.acquisition;
    this.hal = session.instrument.config.hal;
    this.default = session.instrument.config.default;
    this.remoteStores = session.instrument.remote_stores;
    for (const id of this.devices.keys()) if (!Object.hasOwn(session.instrument.devices, id)) this.devices.delete(id);
    for (const [id, state] of Object.entries(session.instrument.devices)) {
      const device = this.devices.get(id);
      const snapshot = this.#snapshotFrom(id, state);
      if (device) device.applySnapshot(snapshot);
      else
        this.devices.set(
          id,
          createDevice(
            this.#client,
            `${this.#base}/devices/${encodeURIComponent(id)}`,
            snapshot,
            () => this.mode === 'capture'
          )
        );
      this.devices.get(id)?.replaceProperties(this.#resultsFrom(state));
    }
    void this.#syncMetadataSchema();
  }

  #statusFrom(session: SessionView): InstrumentStatus {
    return {
      mode: session.instrument.mode,
      active_profile_id: session.instrument.active_profile_id,
      preview_revision: session.instrument.preview_revision,
      fov: session.instrument.fov,
      routing_targets: session.instrument.routing_targets,
      state: session.instrument,
      task_tiles: session.instrument.task_tiles
    };
  }

  #snapshotFrom(id: string, state: DeviceState): import('./types').DeviceSnapshot {
    return { id, connected: true, interface: state.interface, error: null };
  }

  #resultsFrom(state: DeviceState): import('./types').PropResults {
    return {
      results: Object.fromEntries(Object.entries(state.props).map(([name, value]) => [name, { ok: true, value }]))
    };
  }

  // State edits apply server-side; the resulting complete session arrives on the Station feed —
  // no local mutation here, so derived reads converge automatically. Callers handle thrown ApiErrors.

  setActiveProfile(profileId: string): Promise<{ active: string }> {
    return this.#client.post<{ active: string }>(`${this.#base}/profile/active`, { profile_id: profileId });
  }

  /** Shift the stencil mosaic offset so `edge` aligns to a stage position (default: current). µm. */
  alignStencil(edge: AlignEdge, position?: { x: number; y: number }): Promise<void> {
    const { stencil } = this.state;
    const [fovW, fovH] = this.fov ?? [0, 0];
    const lowerLimit = { x: this.stage.x.lowerLimit?.value ?? 0, y: this.stage.y.lowerLimit?.value ?? 0 };
    const pos = position ?? { x: this.stage.x.position?.value ?? 0, y: this.stage.y.position?.value ?? 0 };
    const spacing = { x: fovW * (1 - stencil.overlap_x), y: fovH * (1 - stencil.overlap_y) };
    const { x, y } = alignedOffset(edge, pos, lowerLimit, { x: stencil.x_offset, y: stencil.y_offset }, spacing);
    return this.updateStencil({ x_offset: x, y_offset: y });
  }

  updateProfile(patch: ProfilePatch): Promise<void> {
    return this.#client.patch(`${this.#base}/profile`, patch);
  }

  updateSignals(generatorUid: string, signals: Signals): Promise<void> {
    return this.#client.patch(`${this.#base}/profile/sync/${encodeURIComponent(generatorUid)}`, signals);
  }

  applySettings(): Promise<void> {
    return this.#client.post(`${this.#base}/settings/apply`);
  }

  saveSettings(): Promise<void> {
    return this.#client.post(`${this.#base}/settings/save`);
  }

  applyOpticalRouting(): Promise<void> {
    return this.#client.post(`${this.#base}/optical-routing/apply`);
  }

  updateOpticalRoutingPolicy(dimension: string, policy: OpticalRoutingPolicy): Promise<void> {
    return this.#client.put(`${this.#base}/optical-routing/${encodeURIComponent(dimension)}/policy`, policy);
  }

  overrideOpticalRoute(dimension: string, route: string): Promise<void> {
    return this.#client.post(`${this.#base}/optical-routing/${encodeURIComponent(dimension)}/override`, { route });
  }

  saveAsDefault(): Promise<void> {
    return this.#client.post(`${this.#base}/default/save`, {});
  }

  restoreDefault(): Promise<void> {
    return this.#client.post(`${this.#base}/default/restore`, {});
  }

  savePreset(name: string): Promise<PresetRecord> {
    return this.#client.post<PresetRecord>(`${this.#base}/presets`, { name });
  }

  applyPreset(presetId: string): Promise<void> {
    return this.#client.post(`${this.#base}/presets/${encodeURIComponent(presetId)}/apply`);
  }

  updateChannel(channelId: string, patch: ChannelPatch): Promise<void> {
    return this.#client.patch(`${this.#base}/channels/${encodeURIComponent(channelId)}`, patch);
  }

  updateOutput(patch: WriterPatch): Promise<void> {
    return this.#client.patch(`${this.#base}/output`, patch);
  }

  updateStencil(patch: StencilPatch): Promise<void> {
    return this.#client.patch(`${this.#base}/stencil`, patch);
  }

  updateMetadata(fields: Record<string, unknown>): Promise<void> {
    return this.#client.patch(`${this.#base}/metadata`, fields);
  }

  setMetadataSchema(target: string): Promise<void> {
    return this.#client.put(`${this.#base}/metadata/schema`, { target });
  }

  /** The discovered metadata schema registry (display name → target identifier). */
  fetchMetadataSchemas(): Promise<Record<string, string>> {
    return Promise.resolve(this.metadataSchemas);
  }

  setTraversal(order: TileOrder): Promise<void> {
    return this.#client.put(`${this.#base}/traversal`, { order });
  }

  addTasks(xy: [number, number][], profileIds?: string[]): Promise<void> {
    return this.#client.post(`${this.#base}/tasks`, { xy, profile_ids: profileIds ?? null });
  }

  /** Apply a per-task patch to one or more tasks in a single request. */
  updateTasks(patches: Record<string, TaskPatch>): Promise<void> {
    return this.#client.patch(`${this.#base}/tasks`, { patches });
  }

  /** Delete one or more tasks in a single request. */
  removeTasks(taskIds: string[]): Promise<void> {
    const query = taskIds.map((id) => `ids=${encodeURIComponent(id)}`).join('&');
    return this.#client.del(`${this.#base}/tasks?${query}`);
  }

  /** Launch a run; `request.task_ids=null` captures every planned task in traversal order. */
  async startAcquisition(request: AcquisitionRequest): Promise<ActiveAcquisitionState> {
    const acquisition = await this.#client.post<ActiveAcquisitionState>(`${this.#base}/acquisition`, request);
    this.#onAcquisitionCreated(acquisition.manifest);
    return acquisition;
  }

  stopAcquisition(): Promise<void> {
    return this.#client.post(`${this.#base}/acquisition/stop`);
  }

  dispose(): void {
    // Instrument owns no transport subscriptions; VoxelApp applies complete Station views.
  }

  /** Re-fetch the resolved schema when `metadata_cls` changes; no-op otherwise. */
  async #syncMetadataSchema(): Promise<void> {
    const cls = this.status.state.metadata_cls;
    if (cls === this.#schemaCls) return;
    this.#schemaCls = cls;
    try {
      this.metadataSchema = await this.#client.get<JsonSchema>(
        `${this.#stationBase}/metadata/schema?target=${encodeURIComponent(cls)}`
      );
    } catch {
      this.metadataSchema = null;
    }
  }

  #devicesOfType<T extends DeviceHandle>(ctor: new (...args: never[]) => T): Map<string, T> {
    const out = new SvelteMap<string, T>();
    for (const [id, handle] of this.devices) if (handle instanceof ctor) out.set(id, handle);
    return out;
  }
}

/** Top-level view mode. Snaps and Inpaint hold their own item selection (on their stores); Live is the stream. */
export type PreviewMode = 'live' | 'stage';

export class VoxelApp {
  readonly #client: Client;

  discovery = $state<StationDiscovery>({
    station: { id: '', name: '' },
    instruments: {},
    templates: {},
    colormaps: [],
    metadata_schemas: {},
    realtime: {
      state_websocket_url: '',
      preview_websocket_url: '',
      log_websocket_url: '',
      preview_protocol_version: 1
    }
  });
  /** Persisted acquisition manifests from the catalog, newest first. */
  acquisitions = $state.raw<AcquisitionManifest[]>([]);
  instrument = $state<Instrument | null>(null);
  logs = $state<LogEntry[]>([]);
  error = $state<string | null>(null);
  busy = $state(false);
  /** App-lifetime, IndexedDB-backed collection of captured preview snapshots. */
  readonly snaps = new SnapshotStore();

  /** App-lifetime in-paint mosaics (live-painted per-channel MIP maps). */
  readonly inpaint = new Inpainter();

  // /** Center viewer's top-level mode (Live / Snaps / Inpaint); item selection lives on the stores. */
  // readonly view = new PreviewView(this.snaps);
  readonly viewMode = pref<PreviewMode>('preview:mode', 'live');

  #unsubs: Unsub[] = [];
  #desired = $state<string | null | undefined>(undefined);
  #openName = $state<string | null>(null);
  #stationId = '';
  #latestView: StationFeedView | null = null;
  #logSocket: WebSocket | null = null;
  #logReconnectTimer: number | null = null;
  #disposed = false;
  readonly #lastInstrument = pref<string | null>('last-instrument', null);

  constructor(options: ClientOptions = {}) {
    this.#client = new Client(options);
  }

  get client(): Client {
    return this.#client;
  }

  /** The active instrument's name, or null when none is open. */
  get activeName(): string | null {
    return this.#openName;
  }

  /** The instrument reported by app presence; undefined until the initial presence sync completes. */
  get activeTarget(): string | null | undefined {
    return this.#desired;
  }

  /** Whether initial presence has been hydrated and the local instrument matches it. */
  get ready(): boolean {
    return this.#desired !== undefined && this.#desired === this.#openName;
  }

  /** The last instrument opened in this browser — used to default the launch picker after closing. */
  get lastInstrument(): string | null {
    return this.#lastInstrument.get();
  }

  get stateCursor(): import('./types').StreamCursor {
    return this.#latestView?.cursor ?? { stream_id: '', seq: 0 };
  }

  async initialize(): Promise<void> {
    if (browser) void navigator.storage?.persist?.(); // durable storage so snapshots survive eviction
    this.#unsubs.push(this.#client.onView((view) => this.#applyView(view)));
    this.#unsubs.push(this.#client.onOpen(() => void this.#refreshResources()));
    const stations = await this.#client.get<StationInfo[]>('/stations');
    const station = stations[0];
    if (!station) throw new Error('No control station is available.');
    this.#stationId = station.id;
    await this.#refreshResources();
    this.#connectLogs();
    await this.#client.connect(this.discovery.realtime.state_websocket_url);
    void this.#pruneSnapshots(); // GC snapshots whose instrument no longer exists
  }

  #pushLog(msg: LogEntry): void {
    this.logs.push(msg);
    if (this.logs.length > MAX_LOGS) this.logs.splice(0, this.logs.length - MAX_LOGS);
  }

  /**
   * Hydrate the log backlog on (re)connect and merge it with whatever the live `app.logs` stream has already
   * delivered. Keyed by the journal's durable `seq`, so the overlap dedupes and nothing is missed —
   * the live subscription covers connect-onward, this fills in the history from before connect.
   */
  async #hydrateLogs(): Promise<void> {
    let backlog: LogEntry[];
    try {
      backlog = await this.#client.get<LogEntry[]>(`${this.#stationBase}/logs`);
    } catch {
      return; // logs are diagnostic; the live stream still works without the backlog
    }
    const sorted = [...this.logs, ...backlog].sort((a, b) => a.seq - b.seq);
    const merged: LogEntry[] = [];
    for (const m of sorted) {
      if (merged.length === 0 || merged[merged.length - 1].seq !== m.seq) merged.push(m);
    }
    this.logs = merged.length > MAX_LOGS ? merged.slice(-MAX_LOGS) : merged;
  }

  dispose(): void {
    for (const unsub of this.#unsubs) unsub();
    this.#unsubs = [];
    this.instrument?.dispose();
    this.instrument = null;
    this.#openName = null;
    this.#disposed = true;
    if (this.#logReconnectTimer !== null) clearTimeout(this.#logReconnectTimer);
    this.#logSocket?.close();
    this.#logSocket = null;
    this.inpaint.dispose();
    this.#client.disconnect();
  }

  async retryConnection(): Promise<void> {
    this.#client.resetReconnectState();
    await this.#client.connect(this.discovery.realtime.state_websocket_url);
  }

  /** Load the bounded resources used to initialize the application. */
  async refresh(): Promise<void> {
    this.error = null;
    try {
      await this.#refreshResources();
    } catch (e) {
      this.error = errorMessage(e);
    }
  }

  /** Launch an existing instrument by name. */
  async launch(name: string): Promise<void> {
    await this.#run(() => this.#client.post(`${this.#stationBase}/sessions`, { instrument_name: name }));
  }

  /** Launch a new instrument from a template; `name` defaults to the template's. */
  async launchTemplate(template: string, name?: string): Promise<void> {
    const instrumentName = name ?? template;
    await this.#run(async () => {
      await this.#client.post(`${this.#stationBase}/instruments`, { template, name: instrumentName });
      await this.#client.post(`${this.#stationBase}/sessions`, { instrument_name: instrumentName });
    });
  }

  async archiveState(name: string): Promise<void> {
    await this.#run(() =>
      this.#client.post(`${this.#stationBase}/instruments/${encodeURIComponent(name)}/archive-state`)
    );
    await this.refresh();
  }

  fetchPresets(instrumentName: string): Promise<PresetRecord[]> {
    return this.#client.get<PresetRecord[]>(
      `${this.#stationBase}/instruments/${encodeURIComponent(instrumentName)}/presets`
    );
  }

  createPresetFromAcquisition(acquisitionId: string, name: string): Promise<PresetRecord> {
    return this.#client.post<PresetRecord>(
      `${this.#stationBase}/acquisitions/${encodeURIComponent(acquisitionId)}/presets`,
      { name }
    );
  }

  deletePreset(instrumentName: string, presetId: string): Promise<void> {
    return this.#client.del(
      `${this.#stationBase}/instruments/${encodeURIComponent(instrumentName)}/presets/${encodeURIComponent(presetId)}`
    );
  }

  /** Close the active instrument. */
  async close(): Promise<void> {
    const sessionId = this.instrument?.sessionId;
    if (!sessionId) return;
    await this.#run(() => this.#client.del(`${this.#stationBase}/sessions/${encodeURIComponent(sessionId)}`));
  }

  get #stationBase(): string {
    return `/stations/${encodeURIComponent(this.#stationId)}`;
  }

  async #refreshResources(): Promise<void> {
    if (!this.#stationId) return;
    const [discovery, acquisitions] = await Promise.all([
      this.#client.get<StationDiscovery>(`${this.#stationBase}/discovery`),
      this.#client.get<AcquisitionManifest[]>(`${this.#stationBase}/acquisitions`).catch(() => this.acquisitions)
    ]);
    this.discovery = discovery;
    this.acquisitions = acquisitions;
  }

  /** Sweep persisted snapshots whose instrument no longer exists (frontend-only GC, on connect). */
  async #pruneSnapshots(): Promise<void> {
    try {
      const { instruments } = await this.#client.get<StationDiscovery>(`${this.#stationBase}/discovery`);
      const names = Object.keys(instruments);
      await Promise.all([this.snaps.reconcile(names), this.inpaint.reconcile(names)]);
    } catch {
      // Best-effort: failed discovery just skips this round of GC.
    }
  }

  #applyView(view: StationFeedView): void {
    if (view.station.id !== this.#stationId) return;
    const previous = this.#latestView?.cursor;
    if (previous?.stream_id === view.cursor.stream_id && view.cursor.seq <= previous.seq) return;
    this.#latestView = view;
    this.error = view.error;
    const session = view.session;
    this.#desired = session?.info.instrument_name ?? null;
    if (!session) {
      if (this.instrument) this.instrument.dispose();
      this.instrument = null;
      this.#openName = null;
      this.snaps.scope = null;
      this.inpaint.scope = null;
      this.viewMode.set('live');
      return;
    }
    if (this.instrument?.sessionId === session.info.id) {
      this.instrument.applySession(session);
      return;
    }
    this.instrument?.dispose();
    try {
      this.instrument = new Instrument(
        this.#client,
        session.info.instrument_name,
        session.info.id,
        this.#stationId,
        session,
        this.discovery.metadata_schemas,
        (manifest) => {
          this.acquisitions = [manifest, ...this.acquisitions.filter((candidate) => candidate.id !== manifest.id)];
        }
      );
      this.#openName = session.info.instrument_name;
      this.snaps.scope = this.#openName;
      this.inpaint.scope = this.#openName;
      this.#lastInstrument.set(this.#openName);
    } catch (error) {
      this.instrument = null;
      this.#openName = null;
      this.error = errorMessage(error);
    }
  }

  #connectLogs(): void {
    if (this.#disposed || !this.discovery.realtime.log_websocket_url) return;
    this.#logSocket?.close();
    const socket = new WebSocket(resolveWebSocketUrl(this.discovery.realtime.log_websocket_url));
    socket.binaryType = 'arraybuffer';
    this.#logSocket = socket;
    socket.onopen = () => void this.#hydrateLogs();
    socket.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer)) return;
      this.#pushLog(decodeMsgpack<LogEntry>(new Uint8Array(event.data)));
    };
    socket.onclose = () => {
      if (this.#disposed || this.#logSocket !== socket) return;
      this.#logSocket = null;
      this.#logReconnectTimer = window.setTimeout(() => this.#connectLogs(), 1000);
    };
  }

  async #run(fn: () => Promise<unknown>): Promise<void> {
    this.busy = true;
    this.error = null;
    try {
      await fn();
    } catch (e) {
      this.error = errorMessage(e);
      throw e;
    } finally {
      this.busy = false;
    }
  }
}

const VOXEL_APP_KEY = Symbol('voxel-app');

export function setVoxelApp(app: VoxelApp): void {
  setContext(VOXEL_APP_KEY, app);
}

export function getVoxelApp(): VoxelApp {
  return getContext(VOXEL_APP_KEY);
}
