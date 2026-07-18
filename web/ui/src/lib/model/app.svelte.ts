/** App-level store (`VoxelApp`) + the active-instrument store (`Instrument`) and its device handles. */
import { PersistedState } from 'runed';
import { getContext, setContext } from 'svelte';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import { browser } from '$app/environment';
import { type DeviceRole, type DeviceRoleKind, sortByRoleOrder } from '$lib/model/role';
import { sanitizeString } from '$lib/utils';

import { Client, type ClientOptions, errorMessage, type Unsub } from './client.svelte';
import {
  AnalogOutHandle,
  AxisHandle,
  CameraHandle,
  createDevice,
  type DeviceHandle,
  DiscreteAxisHandle,
  LaserHandle
} from './device.svelte';
import { Inpainter } from './inpaint.svelte';
import { compositeFullFrames, Preview } from './preview.svelte';
import type { SnapshotChannel } from './snapshots.svelte';
import { SnapshotStore } from './snapshots.svelte';
import type {
  AcquisitionProgress,
  AcquisitionRecord,
  AcquisitionRequest,
  AOSignals,
  AppStatus,
  ChannelPatch,
  DeviceSnapshot,
  HALConfig,
  InstrumentsCatalog,
  InstrumentStatus,
  JsonSchema,
  LogMessage,
  ProfilePatch,
  Remote,
  SensorROI,
  StageOrientation,
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

export class Instrument {
  status = $state.raw<InstrumentStatus>(undefined as unknown as InstrumentStatus); // set in the constructor
  hal = $state.raw<HALConfig>(undefined as unknown as HALConfig);

  readonly devices = new SvelteMap<string, DeviceHandle>();

  /** Live preview: frame/tile compositing + viewport/levels/colormap control. */
  readonly preview: Preview;

  /** Live acquisition progress, keyed by `${task}:${profile}` volume. Cleared when a run starts. */
  readonly progress = new SvelteMap<string, AcquisitionProgress>();

  /** The record of the active (or most recent) run — its planned volumes + config snapshot. Set when a
   * run starts; carries the full volume list the progress view fills in. */
  acquisitionRecord = $state.raw<AcquisitionRecord | null>(null);

  readonly mode = $derived(this.status.mode);
  readonly fov = $derived(this.status.fov);
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
  readonly analogOuts = $derived.by(() => this.#devicesOfType(AnalogOutHandle));

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

  /** The stage's mapped axis handles (each carries position + lower/upper limits); undefined if unmapped. */
  readonly stage = $derived.by<{ x?: AxisHandle; y?: AxisHandle; z?: AxisHandle; orientation: StageOrientation }>(
    () => {
      const s = this.hal.stage;
      return {
        x: s.x ? this.axes.get(s.x) : undefined,
        y: s.y ? this.axes.get(s.y) : undefined,
        z: s.z ? this.axes.get(s.z) : undefined,
        // Hardcoded for now — later a per-instrument physical field, read from the backend.
        orientation: DEFAULT_STAGE_ORIENTATION
      };
    }
  );

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

  /** Resolved JSON schema for the active `metadata_cls`; re-fetched from the catalog when it changes. */
  metadataSchema = $state.raw<JsonSchema | null>(null);

  readonly #client: Client;
  #unsubs: Unsub[] = [];
  #schemaCls: string | null = null; // metadata_cls the schema was last fetched for

  constructor(client: Client, status: InstrumentStatus, hal: HALConfig, devices: Record<string, DeviceSnapshot>) {
    this.#client = client;
    this.status = status;
    this.hal = hal;
    for (const [id, snapshot] of Object.entries(devices)) this.devices.set(id, createDevice(client, snapshot));
    this.preview = new Preview(client, hal, status);
    this.#unsubs.push(
      client.on('instrument.status', (s) => {
        this.status = s;
        void this.#syncMetadataSchema();
      })
    );
    this.#unsubs.push(client.on('device.props.update', (u) => this.devices.get(u.device)?.ingest(u.properties)));
    this.#unsubs.push(client.on('acquisition.progress', (p) => this.progress.set(`${p.task}:${p.profile}`, p)));
    void this.#syncMetadataSchema();
  }

  /** Hydrate the active instrument over REST, then keep it fresh from the WS streams. */
  static async open(client: Client): Promise<Instrument> {
    let latest: InstrumentStatus | undefined;
    const buffer = client.on('instrument.status', (s) => (latest = s));
    try {
      const [fetched, hal, devices] = await Promise.all([
        client.get<InstrumentStatus>('/instrument'),
        client.get<HALConfig>('/instrument/hardware'),
        client.get<Record<string, DeviceSnapshot>>('/instrument/devices')
      ]);
      const instrument = new Instrument(client, latest ?? fetched, hal, devices); // a push during the fetch wins
      void instrument.#refreshDevices(); // initial prop values fill in reactively (the feed only pushes changes)
      return instrument;
    } finally {
      buffer();
    }
  }

  /** Re-fetch state + hal + device props over REST — after a reconnect, where pushes may have been missed. */
  async rehydrate(): Promise<void> {
    const [status, hal] = await Promise.all([
      this.#client.get<InstrumentStatus>('/instrument'),
      this.#client.get<HALConfig>('/instrument/hardware')
    ]);
    this.status = status;
    this.hal = hal;
    void this.#refreshDevices();
  }

  // Bench edits: each applies server-side, which re-broadcasts the full state on instrument.status —
  // no local mutation here, so derived reads converge automatically. Callers handle thrown ApiErrors.

  setActiveProfile(profileId: string): Promise<{ active: string }> {
    return this.#client.post<{ active: string }>('/instrument/profile/active', { profile_id: profileId });
  }

  /** Drive the stage to an absolute position (µm); axes omitted from `pos` are left unchanged. */
  moveStage(pos: { x?: number; y?: number; z?: number }): Promise<unknown> {
    const moves: (Promise<unknown> | undefined)[] = [];
    if (pos.x != null) moves.push(this.stage.x?.move(pos.x));
    if (pos.y != null) moves.push(this.stage.y?.move(pos.y));
    if (pos.z != null) moves.push(this.stage.z?.move(pos.z));
    return Promise.all(moves);
  }

  /** Halt all mapped stage axes. */
  haltStage(): Promise<unknown> {
    return Promise.all([this.stage.x?.halt(), this.stage.y?.halt(), this.stage.z?.halt()]);
  }

  /** Shift the stencil mosaic offset so `edge` aligns to a stage position (default: current). µm. */
  alignStencil(edge: AlignEdge, position?: { x: number; y: number }): Promise<void> {
    const { stencil } = this.state;
    const [fovW, fovH] = this.fov ?? [0, 0];
    const lowerLimit = { x: this.stage.x?.lowerLimit?.value ?? 0, y: this.stage.y?.lowerLimit?.value ?? 0 };
    const pos = position ?? { x: this.stage.x?.position?.value ?? 0, y: this.stage.y?.position?.value ?? 0 };
    const spacing = { x: fovW * (1 - stencil.overlap_x), y: fovH * (1 - stencil.overlap_y) };
    const { x, y } = alignedOffset(edge, pos, lowerLimit, { x: stencil.x_offset, y: stencil.y_offset }, spacing);
    return this.updateStencil({ x_offset: x, y_offset: y });
  }

  updateProfile(patch: ProfilePatch): Promise<void> {
    return this.#client.patch('/instrument/profile', patch);
  }

  updateAoSignals(aoUid: string, signals: AOSignals): Promise<void> {
    return this.#client.patch(`/instrument/profile/sync/${encodeURIComponent(aoUid)}`, signals);
  }

  applySettings(): Promise<void> {
    return this.#client.post('/instrument/settings/apply');
  }

  saveSettings(): Promise<void> {
    return this.#client.post('/instrument/settings/save');
  }

  updateChannel(channelId: string, patch: ChannelPatch): Promise<void> {
    return this.#client.patch(`/instrument/channels/${encodeURIComponent(channelId)}`, patch);
  }

  updateOutput(patch: WriterPatch): Promise<void> {
    return this.#client.patch('/instrument/output', patch);
  }

  updateStencil(patch: StencilPatch): Promise<void> {
    return this.#client.patch('/instrument/stencil', patch);
  }

  updateMetadata(fields: Record<string, unknown>): Promise<void> {
    return this.#client.patch('/instrument/metadata', fields);
  }

  setMetadataSchema(target: string): Promise<void> {
    return this.#client.put('/instrument/metadata/schema', { target });
  }

  /** The catalog of selectable metadata schemas (display name → target identifier). */
  async fetchMetadataSchemas(): Promise<Record<string, string>> {
    const { schemas } = await this.#client.get<{ schemas: Record<string, string> }>('/catalog/metadata/schemas');
    return schemas;
  }

  setTraversal(order: TileOrder): Promise<void> {
    return this.#client.put('/instrument/traversal', { order });
  }

  addTasks(xy: [number, number][], profileIds?: string[]): Promise<void> {
    return this.#client.post('/instrument/tasks', { xy, profile_ids: profileIds ?? null });
  }

  /** Apply a per-task patch to one or more tasks in a single request. */
  updateTasks(patches: Record<string, TaskPatch>): Promise<void> {
    return this.#client.patch('/instrument/tasks', { patches });
  }

  /** Delete one or more tasks in a single request. */
  removeTasks(taskIds: string[]): Promise<void> {
    const query = taskIds.map((id) => `ids=${encodeURIComponent(id)}`).join('&');
    return this.#client.del(`/instrument/tasks?${query}`);
  }

  /** Launch a run; `request.task_ids=null` captures every planned task in traversal order. */
  async startAcquisition(request: AcquisitionRequest): Promise<AcquisitionRecord> {
    this.progress.clear();
    const record = await this.#client.post<AcquisitionRecord>('/instrument/acquisition', request);
    this.acquisitionRecord = record;
    return record;
  }

  stopAcquisition(): Promise<void> {
    return this.#client.post('/instrument/acquisition/stop');
  }

  dispose(): void {
    this.preview.dispose();
    for (const unsub of this.#unsubs) unsub();
    this.#unsubs = [];
  }

  async #refreshDevices(): Promise<void> {
    await Promise.all([...this.devices.values()].map((d) => d.refresh().catch(() => undefined)));
  }

  /** Re-fetch the resolved schema when `metadata_cls` changes; no-op otherwise. */
  async #syncMetadataSchema(): Promise<void> {
    const cls = this.status.state.metadata_cls;
    if (cls === this.#schemaCls) return;
    this.#schemaCls = cls;
    try {
      this.metadataSchema = await this.#client.get<JsonSchema>(
        `/catalog/metadata/schema?target=${encodeURIComponent(cls)}`
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
export type PreviewMode = 'live' | 'snaps' | 'inpaint';

/**
 * The center viewer's top-level mode. Item selection lives on the stores — `snaps.activeSnap`,
 * `inpaint.viewed` — so toggling modes preserves each mode's selection for free.
 */
export class PreviewView {
  readonly #snaps!: SnapshotStore;
  // Persisted so the chosen view (Live / Snaps / Inpaint) survives a page refresh.
  readonly #mode = new PersistedState<PreviewMode>('voxel-preview-mode', 'live');

  constructor(snaps: SnapshotStore) {
    this.#snaps = snaps;
  }

  get mode(): PreviewMode {
    return this.#mode.current;
  }

  set mode(value: PreviewMode) {
    this.#mode.current = value;
  }

  get isLive(): boolean {
    return this.mode === 'live';
  }

  /** Whether there's saved snapshot content to enter Snaps mode with. */
  get hasSnaps(): boolean {
    return this.#snaps.hasSnaps;
  }

  /** Switch top-level mode; entering Snaps auto-selects an item if the store has none yet. */
  setMode(mode: PreviewMode): void {
    this.mode = mode;
    if (mode === 'snaps' && !this.#snaps.activeSnap) this.#snaps.selectMostRecent();
    // 'inpaint' auto-select lands with the Inpaint canvas in a later phase.
  }

  goLive(): void {
    this.mode = 'live';
  }
}

export class VoxelApp {
  readonly #client: Client;

  catalog = $state<InstrumentsCatalog>({ instruments: {}, templates: {} });
  instrument = $state<Instrument | null>(null);
  logs = $state<LogMessage[]>([]);
  error = $state<string | null>(null);
  busy = $state(false);
  snapping = $state(false);

  /** App-lifetime, IndexedDB-backed collection of captured preview snapshots. */
  readonly snaps = new SnapshotStore();

  /** App-lifetime in-paint mosaics (live-painted per-channel MIP maps). */
  readonly inpaint = new Inpainter();

  /** Center viewer's top-level mode (Live / Snaps / Inpaint); item selection lives on the stores. */
  readonly view = new PreviewView(this.snaps);

  #unsubs: Unsub[] = [];
  #desired: string | null = null; // latest presence (app.status / GET /app)
  #openName = $state<string | null>(null); // name of the instrument actually open
  #reconciling = false;

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

  /** The last instrument opened in this browser — used to default the launch picker after closing. */
  get lastInstrument(): string | null {
    return browser ? localStorage.getItem('voxel.lastInstrument') : null;
  }

  async initialize(): Promise<void> {
    if (browser) void navigator.storage?.persist?.(); // durable storage so snapshots survive eviction
    this.#unsubs.push(this.#client.on('app.status', (s) => this.#onPresence(s)));
    this.#unsubs.push(this.#client.on('logs', (m) => this.#pushLog(m)));
    this.#unsubs.push(this.#client.onOpen(() => void this.#resync()));
    await this.#client.connect(); // onOpen → #resync hydrates presence + the active instrument
    void this.#pruneSnapshots(); // GC snapshots whose instrument no longer exists
  }

  #pushLog(msg: LogMessage): void {
    this.logs.push(msg);
    if (this.logs.length > MAX_LOGS) this.logs.splice(0, this.logs.length - MAX_LOGS);
  }

  /**
   * Hydrate the log backlog on (re)connect and merge it with whatever the live `logs` stream has already
   * delivered. Keyed by the server's monotonic `seq`, so the overlap dedupes and nothing is missed —
   * the live subscription covers connect-onward, this fills in the history from before connect.
   */
  async #hydrateLogs(): Promise<void> {
    let backlog: LogMessage[];
    try {
      backlog = await this.#client.get<LogMessage[]>('/logs');
    } catch {
      return; // logs are diagnostic; the live stream still works without the backlog
    }
    const sorted = [...this.logs, ...backlog].sort((a, b) => a.seq - b.seq);
    const merged: LogMessage[] = [];
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
    this.inpaint.dispose();
    this.#client.disconnect();
  }

  async retryConnection(): Promise<void> {
    this.#client.resetReconnectState();
    await this.#client.connect();
  }

  /** Configured object stores (name → connection + selectable roots); empty when only local storage. */
  fetchRemotes(): Promise<Record<string, Remote>> {
    return this.#client.get<Record<string, Remote>>('/catalog/remotes');
  }

  /** Load the available instruments and templates. */
  async refresh(): Promise<void> {
    this.error = null;
    try {
      this.catalog = await this.#client.get<InstrumentsCatalog>('/instruments');
    } catch (e) {
      this.error = errorMessage(e);
    }
  }

  /** Launch an existing instrument by name. */
  async launch(name: string): Promise<void> {
    await this.#run(() => this.#client.post(`/instruments/${encodeURIComponent(name)}/launch`));
  }

  /** Launch a new instrument from a template; `name` defaults to the template's. */
  async launchTemplate(template: string, name?: string): Promise<void> {
    const query = name ? `?name=${encodeURIComponent(name)}` : '';
    await this.#run(() => this.#client.post(`/templates/${encodeURIComponent(template)}/launch${query}`));
  }

  /** Close the active instrument. */
  async close(): Promise<void> {
    await this.#run(() => this.#client.post('/close'));
  }

  /**
   * Capture the active instrument's preview into a persisted snapshot (frontend-only): composites the
   * visible channel frames to a JPEG + thumbnail and records stage/profile/channel metadata. When preview
   * is stopped, transiently starts it, waits for frames, captures, then stops it again.
   */
  static readonly SNAPSHOT_THUMB_SIZE = 160;

  async captureSnapshot(): Promise<void> {
    const inst = this.instrument;
    if (!inst || this.snapping) return;
    this.snapping = true;
    const wasIdle = inst.mode === 'idle';
    try {
      if (wasIdle) {
        inst.preview.clearFrames(); // drop stale frames so we wait for images from the current position
        inst.preview.startPreview();
        await this.#awaitPreviewFrames(inst);
      }
      await this.#writeSnapshot(inst);
    } finally {
      if (wasIdle) inst.preview.stopPreview();
      this.snapping = false;
    }
  }

  /** Poll until every visible channel has a frame, or the timeout elapses. */
  async #awaitPreviewFrames(inst: Instrument, timeoutMs = 6000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    const ready = () => {
      const visible = inst.preview.channels.filter((ch) => ch.visible);
      return visible.length > 0 && visible.every((ch) => ch.frame);
    };
    while (!ready() && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }

  async #writeSnapshot(inst: Instrument): Promise<void> {
    const channels = inst.preview.channels;
    const first = channels.find((ch) => ch.visible && ch.frame)?.frame;
    if (!first) throw new Error('No preview frames available');

    const w = first.width;
    const h = first.height;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    compositeFullFrames(ctx, canvas, channels);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/jpeg', 0.85)
    );

    const thumbW = VoxelApp.SNAPSHOT_THUMB_SIZE;
    const thumbH = Math.round((h / w) * thumbW);
    canvas.width = thumbW;
    canvas.height = thumbH;
    compositeFullFrames(ctx, canvas, channels);
    const thumbnail = canvas.toDataURL('image/jpeg', 0.6);

    const profileId = inst.activeProfileId ?? '';

    const snapChannels: Record<string, SnapshotChannel> = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.frame || !ch.name) continue;
      const entry: SnapshotChannel = {
        label: ch.label ?? ch.name,
        colormap: ch.colormap,
        levelsMin: ch.levelsMin,
        levelsMax: ch.levelsMax
      };
      const modelCh = inst.activeChannels.find((c) => c.id === ch.name);
      if (modelCh) {
        entry.detection = {
          deviceId: modelCh.camera.id,
          exposureTime: modelCh.camera.exposure?.value ?? undefined,
          resolution: modelCh.camera.frameSizePx ?? undefined,
          binning: modelCh.camera.binning?.value ?? undefined,
          pixelFormat: modelCh.camera.pixelFormat?.value ?? undefined
        };
        entry.illumination = {
          deviceId: modelCh.laser.id,
          powerSetpoint: modelCh.laser.powerSetpoint?.value ?? undefined,
          power: modelCh.laser.power?.value ?? undefined
        };
      }
      snapChannels[ch.name] = entry;
    }

    this.snaps.add({
      instrument: this.activeName ?? '',
      profileId,
      profileLabel: inst.activeProfile?.label || sanitizeString(profileId),
      stageX: inst.stage.x?.position?.value ?? 0,
      stageY: inst.stage.y?.position?.value ?? 0,
      stageZ: inst.stage.z?.position?.value ?? 0,
      fovW: inst.fov?.[0] ?? 0,
      fovH: inst.fov?.[1] ?? 0,
      channels: snapChannels,
      timestamp: Date.now(),
      blob,
      thumbnail
    });

    if (browser) window.dispatchEvent(new CustomEvent('voxel:snapshot-captured', { detail: { thumbnail } }));
  }

  /** REST re-sync on every (re)connect: refresh presence, then refresh a surviving instrument's state. */
  async #resync(): Promise<void> {
    const existing = this.instrument;
    void this.#hydrateLogs(); // independent of the instrument flow; backlog fills in alongside reconcile
    try {
      this.#desired = (await this.#client.get<AppStatus>('/app')).active;
    } catch (e) {
      this.error = errorMessage(e);
      return;
    }
    await this.#reconcile();
    if (this.instrument && this.instrument === existing) {
      try {
        await this.instrument.rehydrate(); // same instrument survived the gap — catch up on missed pushes
      } catch (e) {
        this.error = errorMessage(e);
      }
    }
  }

  /** Sweep persisted snapshots whose instrument no longer exists (frontend-only GC, on connect). */
  async #pruneSnapshots(): Promise<void> {
    try {
      const { instruments } = await this.#client.get<InstrumentsCatalog>('/instruments');
      const names = Object.keys(instruments);
      await Promise.all([this.snaps.reconcile(names), this.inpaint.reconcile(names)]);
    } catch {
      // best-effort — a failed catalog fetch just skips this round of GC
    }
  }

  #onPresence(status: AppStatus): void {
    this.#desired = status.active;
    void this.#reconcile();
  }

  /** Converge the open instrument to `#desired`. Single-flight; re-checks `#desired` across awaits. */
  async #reconcile(): Promise<void> {
    if (this.#reconciling) return;
    this.#reconciling = true;
    try {
      while (this.#desired !== this.#openName) {
        const target = this.#desired;
        if (this.instrument) {
          this.instrument.dispose();
          this.instrument = null;
          this.#openName = null;
          this.snaps.scope = null;
          this.inpaint.scope = null;
          this.view.goLive(); // the previous instrument's view shouldn't linger
        }
        if (target === null) continue;
        let opened: Instrument | null = null;
        try {
          opened = await Instrument.open(this.#client);
        } catch (e) {
          this.error = errorMessage(e);
        }
        if (this.#desired !== target) {
          opened?.dispose(); // presence moved on during the open — discard and re-reconcile
          continue;
        }
        if (opened === null) break; // open failed; retry on the next presence / reconnect
        this.instrument = opened;
        this.#openName = target;
        this.snaps.scope = target;
        this.inpaint.scope = target;
        if (browser) localStorage.setItem('voxel.lastInstrument', target);
      }
    } finally {
      this.#reconciling = false;
    }
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
