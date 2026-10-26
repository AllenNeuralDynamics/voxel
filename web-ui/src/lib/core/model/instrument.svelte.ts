/** The open instrument: its session, devices, channels, profiles, routing and tasks. */
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import { reportFailure } from '$lib/core/failures';
import { displayName } from '$lib/core/utils/helpers';

import { Client } from './client.svelte';
import {
  AxisHandle,
  CameraHandle,
  createDevice,
  type DeviceHandle,
  DiscreteAxisHandle,
  LaserHandle,
  SignalGeneratorHandle
} from './device.svelte';
import { assignDeviceRoles, type DeviceRoleAssignment } from './device-rules';
import { createEditQueue } from './edit-queue.svelte';
import { ProfileLinks } from './profile-links.svelte';
import { type EditContext, EnumeratedModel, NumericModel } from './prop.svelte';
import { Stage, type StageAxis } from './stage.svelte';
import type {
  AcquisitionManifest,
  AcquisitionRequest,
  AcquisitionTask,
  Change,
  ChannelPatch,
  DeviceState,
  HALConfig,
  InstrumentDefaults,
  InstrumentStatus,
  JsonSchema,
  OpticalRouteConfig,
  PresetRecord,
  ProfilePatch,
  RoutingDimensionConfig,
  RoutingRule,
  SensorROI,
  SessionView,
  Signals,
  TaskPatch,
  WriterPatch
} from './types';
import { DEFAULT_STAGE_ORIENTATION } from './types';

/** A filter wheel and the filter that a channel sets on it. */
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
  /** Writable properties whose user edits are saved automatically. */
  autosave: Set<string>;
  /** Properties whose live values differ from existing saved values. */
  changed: Set<string>;
  /** Live camera ROI differs from the profile's ROI. */
  roiChanged: boolean;
}

/** A stable routing editor with derived rule choice and hardware observations. */
export interface RoutingDimension {
  readonly id: string;
  readonly model: NumericModel | EnumeratedModel<string>;
  readonly axis: 'x' | 'y' | undefined;
  readonly routes: readonly string[];
  routeLabel(route: string): string;
  /** Rule choice; split rules require a known stage position. */
  readonly resolved: string | undefined;
  /** Uniquely matched, settled hardware route; absent for missing or ambiguous readback. */
  readonly current: string | undefined;
  readonly moving: boolean;
}

/** Compare two property values; treats floating-point near-equality as equal. */
function propValueDiverged(saved: unknown, current: unknown): boolean {
  if (saved === undefined || saved === null) return false;
  if (current === undefined || current === null) return false;
  if (typeof saved === 'number' && typeof current === 'number') return Math.abs(saved - current) > 1e-6;
  return saved !== current;
}

/** Compare live ROI to the saved ROI, defaulting to the full sensor when absent. */
function roiDiffers(
  saved: SensorROI | undefined,
  live: SensorROI | undefined,
  sensor?: { x: number; y: number }
): boolean {
  if (!live) return false;
  if (!saved) {
    // Profiles without an explicit ROI use the full sensor.
    if (!sensor) return false;
    return !(live.x === 0 && live.y === 0 && live.w === sensor.x && live.h === sensor.y);
  }
  return saved.x !== live.x || saved.y !== live.y || saved.w !== live.w || saved.h !== live.h;
}

export class Instrument {
  status = $state.raw<InstrumentStatus>(undefined as unknown as InstrumentStatus); // set in the constructor
  hal = $state.raw<HALConfig>(undefined as unknown as HALConfig);
  default = $state.raw<InstrumentDefaults>(undefined as unknown as InstrumentDefaults);

  readonly devices = new SvelteMap<string, DeviceHandle>();
  readonly links = new ProfileLinks();
  /** Session-owned rule editors; numeric values and bounds are in micrometres. */
  readonly routingDimensions = new SvelteMap<string, RoutingDimension>();

  /** What the instrument is doing; a capture also carries its transient progress. */
  readonly activity = $derived(this.status.activity);
  /** Whether a capture owns the hardware, so manual changes are rejected. */
  readonly busy = $derived(this.activity.kind === 'capture');
  /** Active-profile channels that preview runs, in profile order. */
  readonly previewChannels = $derived(this.status.preview_channels);
  readonly fov = $derived(this.status.fov);
  readonly state = $derived(this.status.state);
  readonly plan = $derived(this.state.plan);
  readonly profileFovs = $derived(this.status.profile_fovs);
  readonly plannedVolumes = $derived(this.status.planned_volumes);
  readonly history = $derived(this.status.history);
  readonly edits = createEditQueue();
  readonly imaging = $derived(this.state.imaging);
  readonly activeProfileId = $derived(this.status.active_profile_id);
  readonly activeProfile = $derived(this.activeProfileId ? this.imaging.profiles[this.activeProfileId] : undefined);

  // Devices grouped by intrinsic type — stable for the instrument's lifetime.
  readonly cameras = $derived.by(() => this.#devicesOfType(CameraHandle));
  readonly lasers = $derived.by(() => this.#devicesOfType(LaserHandle));
  readonly axes = $derived.by(() => this.#devicesOfType(AxisHandle));
  readonly discreteAxes = $derived.by(() => this.#devicesOfType(DiscreteAxisHandle));
  readonly signalGenerators = $derived.by(() => this.#devicesOfType(SignalGeneratorHandle));

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
          label: ch.label || displayName(id),
          emission: ch.emission ?? undefined,
          camera,
          laser,
          filters,
          auxilliary
        }
      ];
    });
  });

  // Saved-value comparisons and autosave policy for active-profile devices.
  readonly divergence = $derived.by<Map<string, DeviceDivergence>>(() => {
    const out = new SvelteMap<string, DeviceDivergence>();
    const profile = this.activeProfile;
    if (!profile) return out;
    const configs = {
      ...this.hal.devices,
      ...Object.fromEntries(Object.values(this.hal.nodes).flatMap((node) => Object.entries(node.devices)))
    };
    const add = (device: DeviceHandle): void => {
      if (out.has(device.id)) return;
      const saved = profile.props[device.id] ?? {};
      const selection = configs[device.id]?.autosave ?? [];
      const autosave = new SvelteSet<string>();
      const changed = new SvelteSet<string>();
      for (const [name, prop] of device.props) {
        if (prop.access !== 'rw' || name === 'roi' || name === 'roi_grid') continue;
        if (selection === '*' || selection.includes(name)) autosave.add(name);
        if (Object.hasOwn(saved, name) && propValueDiverged(saved[name], prop.value)) changed.add(name);
      }
      const roiChanged =
        device instanceof CameraHandle &&
        roiDiffers(profile.rois[device.id], device.roi.value, device.sensorSizePx ?? undefined);
      out.set(device.id, { saved, autosave, changed, roiChanged });
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

  /** Resolved JSON schema for the active `metadata_cls`; re-fetched from the backend when it changes. */
  metadataSchema = $state.raw<JsonSchema | null>(null);
  remoteStores = $state.raw<Record<string, import('./types').Remote>>({});

  readonly #client: Client;
  readonly #base: string;
  readonly #stationBase: string;
  readonly #onAcquisitionCreated: (manifest: AcquisitionManifest) => void;
  /** Frozen for the open session so every handle keeps a stable role and color index across state updates. */
  readonly #deviceRoles: ReadonlyMap<string, DeviceRoleAssignment>;
  #schemaCls: string | null = null; // metadata_cls the schema was last fetched for

  constructor(
    client: Client,
    readonly id: string,
    readonly sessionId: string,
    readonly stationId: string,
    session: SessionView,
    /** The discovered metadata schema registry (display name → target identifier). */
    readonly metadataSchemas: Record<string, string>,
    onAcquisitionCreated: (manifest: AcquisitionManifest) => void
  ) {
    this.#client = client;
    this.#stationBase = `/stations/${encodeURIComponent(stationId)}`;
    this.#base = `${this.#stationBase}/sessions/${encodeURIComponent(sessionId)}/instrument`;
    this.#onAcquisitionCreated = onAcquisitionCreated;
    this.status = this.#statusFrom(session);
    this.hal = session.instrument.config.hal;
    this.default = session.instrument.config.default;
    this.#deviceRoles = assignDeviceRoles(this.hal, this.state.imaging);
    this.remoteStores = session.instrument.remote_stores;
    for (const [deviceId, device] of Object.entries(session.instrument.devices)) {
      const base = `${this.#base}/devices/${encodeURIComponent(deviceId)}`;
      this.devices.set(
        deviceId,
        createDevice(client, base, this.#snapshotFrom(deviceId, device), () => this.busy, this.#roleFor(deviceId))
      );
      this.devices.get(deviceId)?.replaceProperties(this.#resultsFrom(device));
    }
    const sx = this.#stageAxis('x');
    const sy = this.#stageAxis('y');
    const sz = this.#stageAxis('z');
    if (!sx || !sy || !sz) throw new Error('Instrument stage must map all three (X/Y/Z) axes');
    this.stage = new Stage(sx, sy, sz, () => this.fov, DEFAULT_STAGE_ORIENTATION);
    this.#syncProfileLinks();
    this.#syncRoutingDimensions();
    void this.#syncMetadataSchema();
  }

  /** Replace every runtime field from one authoritative complete Station session view. */
  applySession(session: SessionView): void {
    if (session.info.id !== this.sessionId) return;
    this.status = this.#statusFrom(session);
    this.hal = session.instrument.config.hal;
    this.default = session.instrument.config.default;
    this.remoteStores = session.instrument.remote_stores;
    for (const [id, device] of this.devices) {
      if (Object.hasOwn(session.instrument.devices, id)) continue;
      device.dispose();
      this.devices.delete(id);
    }
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
            () => this.busy,
            this.#roleFor(id)
          )
        );
      this.devices.get(id)?.replaceProperties(this.#resultsFrom(state));
    }
    this.#syncProfileLinks();
    this.#syncRoutingDimensions();
    void this.#syncMetadataSchema();
  }

  #syncProfileLinks(): void {
    this.links.sync(
      this.activeProfileId,
      this.activeChannels.map((channel) => channel.camera)
    );
  }

  #statusFrom(session: SessionView): InstrumentStatus {
    return {
      activity: session.instrument.activity,
      active_profile_id: session.instrument.active_profile_id,
      preview_channels: session.instrument.preview_channels,
      stream_revision: session.instrument.stream_revision,
      fov: session.instrument.fov,
      // Keep persisted state separate from the session's hardware and runtime fields.
      state: {
        imaging: session.instrument.imaging,
        routing: session.instrument.routing,
        metadata_cls: session.instrument.metadata_cls,
        output: session.instrument.output,
        plan: session.instrument.plan,
        metadata: session.instrument.metadata,
        last_modified: session.instrument.last_modified
      },
      profile_fovs: session.instrument.profile_fovs,
      planned_volumes: session.instrument.planned_volumes,
      history: session.instrument.history
    };
  }

  #roleFor(deviceId: string): DeviceRoleAssignment {
    return this.#deviceRoles.get(deviceId) ?? { role: 'other', roleIndex: 0 };
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

  undo(): Promise<void> {
    if (this.edits.pending) return Promise.reject(new Error('Wait for edits to finish saving'));
    return this.edits.run(() => this.#client.post(`${this.#base}/undo`));
  }

  redo(): Promise<void> {
    if (this.edits.pending) return Promise.reject(new Error('Wait for edits to finish saving'));
    return this.edits.run(() => this.#client.post(`${this.#base}/redo`));
  }

  setActiveProfile(profileId: string): Promise<{ active: string }> {
    return this.edits.run(() =>
      this.#client.post<{ active: string }>(`${this.#base}/profile/active`, { profile_id: profileId })
    );
  }

  updateProfile(patch: ProfilePatch): Promise<Change<[string, ProfilePatch]>> {
    return this.edits.run(() => this.#client.patch<Change<[string, ProfilePatch]>>(`${this.#base}/profile`, patch));
  }

  updateSignals(generatorUid: string, signals: Signals): Promise<void> {
    return this.#client.patch(`${this.#base}/profile/sync/${encodeURIComponent(generatorUid)}`, signals);
  }

  applySettings(): Promise<void> {
    return this.edits.run(() => this.#client.post(`${this.#base}/settings/apply`));
  }

  applyRoutingRule(dimension?: string): Promise<void> {
    const query = dimension === undefined ? '' : `?dimension=${encodeURIComponent(dimension)}`;
    return this.edits.run(() => this.#client.post(`${this.#base}/routing/apply${query}`));
  }

  #setRoutingRule(
    dimension: string,
    rule: RoutingRule,
    { editId }: EditContext = {}
  ): Promise<Change<RoutingRule | null>> {
    const query = editId ? `?edit_id=${encodeURIComponent(editId)}` : '';
    return this.edits.run(() =>
      this.#client.put<Change<RoutingRule | null>>(
        `${this.#base}/routing/${encodeURIComponent(dimension)}/rule${query}`,
        rule
      )
    );
  }

  selectRoute(dimension: string, route: string): Promise<void> {
    return this.#client.post(`${this.#base}/routing/${encodeURIComponent(dimension)}/select`, { route });
  }

  /** Choose which active-profile channels preview runs; a running preview restarts with them. */
  setPreviewChannels(channelIds: string[]): Promise<void> {
    return this.#client.put(`${this.#base}/preview/channels`, { channel_ids: channelIds });
  }

  saveAsDefault(): Promise<void> {
    return this.edits.run(() => this.#client.post(`${this.#base}/default/save`, {}));
  }

  restoreDefault(): Promise<void> {
    return this.edits.run(() => this.#client.post(`${this.#base}/default/restore`, {}));
  }

  savePreset(name: string): Promise<PresetRecord> {
    return this.edits.run(() => this.#client.post<PresetRecord>(`${this.#base}/presets`, { name }));
  }

  applyPreset(presetId: string): Promise<void> {
    return this.edits.run(() => this.#client.post(`${this.#base}/presets/${encodeURIComponent(presetId)}/apply`));
  }

  updateChannel(channelId: string, patch: ChannelPatch): Promise<Change<ChannelPatch>> {
    return this.edits.run(() =>
      this.#client.patch<Change<ChannelPatch>>(`${this.#base}/channels/${encodeURIComponent(channelId)}`, patch)
    );
  }

  updateOutput(patch: WriterPatch): Promise<Change<WriterPatch>> {
    return this.edits.run(() => this.#client.patch<Change<WriterPatch>>(`${this.#base}/output`, patch));
  }

  updateMetadata(fields: Record<string, unknown>): Promise<Change<Record<string, unknown>>> {
    return this.edits.run(() => this.#client.patch<Change<Record<string, unknown>>>(`${this.#base}/metadata`, fields));
  }

  setMetadataSchema(target: string): Promise<void> {
    return this.edits.run(() => this.#client.put(`${this.#base}/metadata/schema`, { target }));
  }

  addTask(task: AcquisitionTask): Promise<Change<AcquisitionTask[]>> {
    return this.edits.run(() => this.#client.post<Change<AcquisitionTask[]>>(`${this.#base}/tasks`, task));
  }

  updateTask(taskId: string, patch: TaskPatch, { editId }: EditContext = {}): Promise<Change<AcquisitionTask>> {
    const query = editId ? `?edit_id=${encodeURIComponent(editId)}` : '';
    return this.edits.run(() =>
      this.#client.patch<Change<AcquisitionTask>>(`${this.#base}/tasks/${encodeURIComponent(taskId)}${query}`, patch)
    );
  }

  reorderTasks(taskIds: string[]): Promise<Change<AcquisitionTask[]>> {
    return this.edits.run(() =>
      this.#client.put<Change<AcquisitionTask[]>>(`${this.#base}/tasks/order`, { ids: taskIds })
    );
  }

  /** Delete one or more tasks in a single request. */
  removeTasks(taskIds: string[]): Promise<Change<AcquisitionTask[]>> {
    const query = taskIds.map((id) => `ids=${encodeURIComponent(id)}`).join('&');
    return this.edits.run(() => this.#client.del<Change<AcquisitionTask[]>>(`${this.#base}/tasks?${query}`));
  }

  /**
   * Launch a run; `request.task_ids=null` captures every planned task in traversal order. It waits in the edit queue,
   * so the run uses every edit made before it.
   */
  async startAcquisition(request: AcquisitionRequest): Promise<AcquisitionManifest> {
    const manifest = await this.edits.run(() =>
      this.#client.post<AcquisitionManifest>(`${this.#base}/acquisition`, request)
    );
    this.#onAcquisitionCreated(manifest);
    return manifest;
  }

  stopAcquisition(): Promise<void> {
    return this.#client.post(`${this.#base}/acquisition/stop`);
  }

  dispose(): void {
    this.links.clear();
    for (const dimension of this.routingDimensions.values()) dimension.model.dispose();
    this.routingDimensions.clear();
    for (const device of this.devices.values()) device.dispose();
    this.devices.clear();
    this.edits.dispose();
  }

  #createRoutingDimension(id: string, definition: RoutingDimensionConfig, rule: RoutingRule): RoutingDimension {
    const assignments: Record<string, OpticalRouteConfig> = definition.routes;
    const routes = Object.keys(assignments);
    const axis = definition.type === 'select' ? undefined : definition.type === 'split-x' ? 'x' : 'y';
    const disabled = () => this.busy;
    let model: NumericModel | EnumeratedModel<string>;
    if (definition.type === 'select' && 'selected' in rule) {
      model = new EnumeratedModel(rule.selected, routes, {
        disabled,
        onPatch: (selected, context) => reportFailure(this.#setRoutingRule(id, { selected }, context))
      });
    } else if (axis && 'threshold' in rule) {
      model = new NumericModel(rule.threshold, {
        disabled,
        step: 100,
        throttleMs: 100,
        onEditStart: () => this.edits.hold(),
        onPatch: (threshold, context) => reportFailure(this.#setRoutingRule(id, { threshold }, context))
      });
    } else {
      throw new Error(`Routing rule does not match dimension '${id}'`);
    }

    const selectorIds = [...new SvelteSet(Object.values(assignments).flatMap((route) => Object.keys(route.selectors)))];
    const selector = (uid: string) => this.discreteAxes.get(uid);
    const position = () => (axis ? this.stage.axis(axis).position?.value : undefined);
    return {
      id,
      model,
      axis,
      routes,
      routeLabel: (route) => assignments[route]?.label ?? displayName(route),
      get resolved() {
        if (model instanceof EnumeratedModel) return model.value;
        const value = position();
        return value != null && Number.isFinite(value) ? (value < model.value ? 'lower' : 'upper') : undefined;
      },
      get current() {
        const positions = new SvelteMap<string, string>();
        for (const uid of selectorIds) {
          const handle = selector(uid);
          const state = handle?.state;
          if (!handle || !state || state.is_moving || state.position === null) return undefined;
          const label = handle.labelAt(state.position);
          if (label == null) return undefined;
          positions.set(uid, label);
        }
        const matches = routes.filter((route) =>
          Object.entries(assignments[route].selectors).every(([uid, label]) => positions.get(uid) === label)
        );
        return matches.length === 1 ? matches[0] : undefined;
      },
      get moving() {
        return selectorIds.some((uid) => selector(uid)?.state?.is_moving === true);
      }
    };
  }

  /** Synchronize dimension models from the current session without publishing edits. */
  #syncRoutingDimensions(): void {
    for (const [id, dimension] of this.routingDimensions) {
      if (this.hal.optical_routing[id] && this.state.routing[id]) continue;
      dimension.model.dispose();
      this.routingDimensions.delete(id);
    }
    for (const [id, definition] of Object.entries(this.hal.optical_routing)) {
      const rule = this.state.routing[id];
      if (!rule) continue;
      let dimension = this.routingDimensions.get(id);
      if (!dimension) {
        dimension = this.#createRoutingDimension(id, definition, rule);
        this.routingDimensions.set(id, dimension);
      }
      if (dimension.model instanceof NumericModel && dimension.axis && 'threshold' in rule) {
        const axis = this.stage.axis(dimension.axis);
        dimension.model.update({
          kind: 'float',
          value: rule.threshold,
          minimum: axis.lowerLimit?.value ?? null,
          maximum: axis.upperLimit?.value ?? null
        });
      } else if (dimension.model instanceof EnumeratedModel && 'selected' in rule) {
        dimension.model.update({ kind: 'string', value: rule.selected });
      }
    }
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
