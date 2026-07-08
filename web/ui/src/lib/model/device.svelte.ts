/** App-level store (`VoxelApp`) + the active-instrument store (`Instrument`) and its device handles. */
import { SvelteMap } from 'svelte/reactivity';

import { wavelengthToColor } from '$lib/utils';
import { parseVec2D, type Vec2D } from '$lib/utils/vec';

import { Client } from './client.svelte';
import {
  type AnyPropModel,
  BoolModel,
  createPropModel,
  EnumeratedModel,
  LinkGroup,
  NumericModel,
  Prop,
  type PropSnapshot
} from './prop.svelte';
import type { AOSignals, DeviceInterface, DeviceSnapshot, PropResult, PropResults, SensorROI } from './types';

/**
 * A single device: its introspected interface plus a live, reactive cache of property models.
 * Reads come off `props` (kept fresh by `device.props.update`); writes (`setProps`, `runCommand`)
 * go out over REST. Role/accent are NOT carried here — those are profile-derived on `Instrument`.
 */
export class DeviceHandle {
  readonly id: string;
  connected = $state(false);
  error = $state<string | undefined>(undefined);
  interface = $state<DeviceInterface | undefined>(undefined);
  props = new SvelteMap<string, Prop>();

  #client: Client;

  constructor(client: Client, snapshot: DeviceSnapshot) {
    this.#client = client;
    this.id = snapshot.id;
    this.applySnapshot(snapshot);
  }

  applySnapshot(snapshot: DeviceSnapshot): void {
    this.connected = snapshot.connected;
    this.interface = snapshot.interface ?? undefined;
    this.error = snapshot.error ?? undefined;
  }

  getProp(name: string): Prop | undefined {
    return this.props.get(name);
  }

  /** Merge a `PropResults` payload (a stream push or a fetch) into the prop cache. */
  ingest(results: PropResults): void {
    for (const [name, result] of Object.entries(results.results)) {
      if (!result.ok) continue; // error envelope — skip
      this.#upsert(name, result.value);
    }
  }

  /** Fetch property values over REST and merge them; all properties when `names` is empty. */
  async refresh(...names: string[]): Promise<void> {
    const query = names.length ? `?${names.map((n) => `props=${encodeURIComponent(n)}`).join('&')}` : '';
    this.ingest(await this.#client.get<PropResults>(`${this.#base}/properties${query}`));
  }

  async setProps(properties: Record<string, unknown>): Promise<void> {
    this.ingest(await this.#client.patch<PropResults>(`${this.#base}/properties`, { properties }));
  }

  runCommand(name: string, args: unknown[] = [], kwargs: Record<string, unknown> = {}): Promise<unknown> {
    return this.#client.post<unknown>(`${this.#base}/commands/${encodeURIComponent(name)}`, { args, kwargs });
  }

  get #base(): string {
    return `/instrument/devices/${encodeURIComponent(this.id)}`;
  }

  #upsert(name: string, snapshot: PropSnapshot<unknown>): void {
    const existing = this.props.get(name);
    if (existing) {
      existing.model.update(snapshot);
      return;
    }
    const info = this.interface?.properties?.[name];
    if (!info) return;
    const model = createPropModel(snapshot, (value) => void this.setProps({ [name]: value }));
    this.props.set(name, new Prop(model, info));
  }

  /** Read a property's model and assert its concrete type; `undefined` on mismatch/absence. */
  protected typedProp<T extends AnyPropModel>(name: string, ctor: new (...args: never[]) => T): T | undefined {
    const model = this.getProp(name)?.model;
    return model instanceof ctor ? model : undefined;
  }
}

export class AxisHandle extends DeviceHandle {
  position = $derived.by(() => this.typedProp('position', NumericModel));
  lowerLimit = $derived.by(() => this.typedProp('lower_limit', NumericModel));
  upperLimit = $derived.by(() => this.typedProp('upper_limit', NumericModel));
  isMoving = $derived.by(() => this.typedProp('is_moving', BoolModel));
  range = $derived((this.upperLimit?.value ?? 100) - (this.lowerLimit?.value ?? 0));

  /** Move to an absolute position, clamped to soft limits. */
  move(position: number): Promise<unknown> {
    const lower = this.lowerLimit?.value ?? 0;
    const upper = this.upperLimit?.value ?? 100;
    return this.runCommand('move_abs', [Math.max(lower, Math.min(upper, position))], { wait: false });
  }

  halt(): Promise<unknown> {
    return this.runCommand('halt');
  }
}

/** A fixed-position device (filter wheel, turret, slider): an int `position` plus a label map. */
export class DiscreteAxisHandle extends DeviceHandle {
  position = $derived.by(() => this.typedProp('position', NumericModel));
  isMoving = $derived.by(() => this.typedProp('is_moving', BoolModel));

  /** The current slot's label, or null at an unlabeled slot. */
  label = $derived.by<string | null>(() => {
    const v = this.getProp('label')?.value;
    return typeof v === 'string' ? v : null;
  });

  /** Slot index → label (null for unlabeled slots). */
  labels = $derived.by<Record<string, string | null>>(() => {
    const v = this.getProp('labels')?.value;
    return v && typeof v === 'object' ? (v as Record<string, string | null>) : {};
  });

  /** Move to a slot by index. */
  move(slot: number): Promise<unknown> {
    return this.runCommand('move', [slot], { wait: false });
  }

  /** Move to a slot by label. */
  select(label: string): Promise<unknown> {
    return this.runCommand('select', [label], { wait: false });
  }

  halt(): Promise<unknown> {
    return this.runCommand('halt');
  }
}

type Sample = { t: number; v: number };

/** Rolling telemetry window + point cap, shared by laser power and camera stream sparklines. */
const HISTORY_WINDOW_MS = 60_000;
const HISTORY_MAX = 600;

/** Whether a wire result carries a value (vs. an error envelope). */
const isFresh = (r: PropResult | undefined): boolean => r != null && r.ok;

/** Append a sample, dropping points older than the window (keeping one just outside so the trace spans the left edge), capped at `max` points. */
function pushSample(series: Sample[], t: number, v: number, windowMs = HISTORY_WINDOW_MS, max = HISTORY_MAX): Sample[] {
  const cutoff = t - windowMs;
  const next = [...series, { t, v }];
  let start = 0;
  while (start < next.length - 1 && next[start + 1].t < cutoff) start++;
  const windowed = start > 0 ? next.slice(start) : next;
  return windowed.length > max ? windowed.slice(-max) : windowed;
}

export class LaserHandle extends DeviceHandle {
  static readonly HISTORY_WINDOW_MS = HISTORY_WINDOW_MS;
  static readonly HISTORY_MAX = HISTORY_MAX;

  powerHistory = $state<Sample[]>([]);
  setpointHistory = $state<Sample[]>([]);

  power = $derived.by(() => this.typedProp('power', NumericModel));
  powerSetpoint = $derived.by(() => this.typedProp('power_setpoint', NumericModel));
  isEnabled = $derived.by(() => this.typedProp('is_enabled', BoolModel));
  wavelength = $derived.by(() => this.typedProp('wavelength', NumericModel));
  temperature = $derived.by(() => this.typedProp('temperature_c', NumericModel));

  color = $derived.by((): string | undefined => {
    const wl = this.wavelength?.value;
    return typeof wl === 'number' ? wavelengthToColor(wl) : undefined;
  });

  hasHistory = $derived(this.powerHistory.length > 1);
  maxPower = $derived(this.powerSetpoint?.max ?? this.power?.max ?? 100);

  enable(): Promise<unknown> {
    return this.runCommand('enable');
  }

  disable(): Promise<unknown> {
    return this.runCommand('disable');
  }

  toggle(): Promise<unknown> {
    return this.isEnabled?.value ? this.disable() : this.enable();
  }

  /** Record measured power and setpoint into their time-series whenever the stream reports them. */
  ingest(results: PropResults): void {
    super.ingest(results);
    const t = performance.now();
    const r = results.results;
    if (isFresh(r.power) && typeof this.power?.value === 'number') {
      this.powerHistory = pushSample(this.powerHistory, t, this.power.value);
    }
    if (isFresh(r.power_setpoint) && typeof this.powerSetpoint?.value === 'number') {
      this.setpointHistory = pushSample(this.setpointHistory, t, this.powerSetpoint.value);
    }
  }
}

export type AOState = 'fresh' | 'ready' | 'running';

export class AnalogOutHandle extends DeviceHandle {
  /** Currently loaded signals; `null` when fresh or after a failed load. */
  loaded = $derived.by<AOSignals | null>(() => (this.getProp('loaded')?.value ?? null) as AOSignals | null);

  state = $derived.by<AOState>(() => {
    const v = this.getProp('state')?.value;
    return (typeof v === 'string' ? v : 'fresh') as AOState;
  });

  voltageRange = $derived.by<{ min: number; max: number } | null>(() => {
    const v = this.getProp('voltage_range')?.value;
    return v && typeof v === 'object' && 'min' in v && 'max' in v ? (v as { min: number; max: number }) : null;
  });

  isRunning = $derived(this.state === 'running');
}

export type CameraMode = 'IDLE' | 'PREVIEW' | 'ACQUISITION';

export interface IntRange {
  min: number;
  max: number;
  step: number;
}

export interface ROIGrid {
  h: IntRange;
  v: IntRange;
}

/** Intersect two int ranges: tightest bounds, coarsest step. */
function mergeRange(a: IntRange, b: IntRange): IntRange {
  return { min: Math.max(a.min, b.min), max: Math.min(a.max, b.max), step: Math.max(a.step, b.step) };
}

/** Clamp `v` into [min, max] and snap to `step` (snapping relative to `min`). */
function clampSnap(v: number, min: number, max: number, step: number): number {
  let out = Math.min(max, Math.max(min, v));
  if (step > 0) {
    out = min + Math.round((out - min) / step) * step;
    out = Math.min(max, Math.max(min, out));
  }
  return out;
}

/**
 * The camera sensor ROI as a linkable model — the sole ROI entry point on CameraHandle.
 * Reads come off the live `roi`/`roi_grid` props; writes go through the `update_roi` command.
 * When linked into a LinkGroup, explicit edits fan out to every peer clamped to the intersection
 * of all peers' grids, while center/reset compute per-camera against each sensor.
 */
export class RoiModel {
  group: LinkGroup<RoiModel> | undefined = $state(undefined);

  #camera: CameraHandle;

  constructor(camera: CameraHandle) {
    this.#camera = camera;
  }

  /** Live ROI from the camera's `roi` prop; undefined until it hydrates. */
  get value(): SensorROI | undefined {
    const v = this.#camera.getProp('roi')?.value;
    return v && typeof v === 'object' ? (v as SensorROI) : undefined;
  }

  /** This camera's own hardware grid from the `roi_grid` prop. */
  get ownGrid(): ROIGrid | undefined {
    const v = this.#camera.getProp('roi_grid')?.value;
    return v && typeof v === 'object' ? (v as ROIGrid) : undefined;
  }

  /** Effective grid: own, intersected with peers' grids when linked (tightest bounds win). */
  get grid(): ROIGrid | undefined {
    const own = this.ownGrid;
    if (!own || !this.group) return own;
    let h = own.h;
    let v = own.v;
    for (const peer of this.group.members) {
      if (peer === this) continue;
      const pg = peer.ownGrid;
      if (!pg) continue;
      h = mergeRange(h, pg.h);
      v = mergeRange(v, pg.v);
    }
    return { h, v };
  }

  /** Sensor size in pixels — the extent center/reset work against. */
  get sensor(): Vec2D | null {
    return this.#camera.sensorSizePx;
  }

  /** Clamp+snap an ROI to the (merged) grid, keeping the origin within sensor extents. */
  resolve(roi: SensorROI): SensorROI {
    const grid = this.grid;
    if (!grid) return roi;
    const w = clampSnap(roi.w, grid.h.min, grid.h.max, grid.h.step);
    const h = clampSnap(roi.h, grid.v.min, grid.v.max, grid.v.step);
    const x = clampSnap(roi.x, 0, grid.h.max - w, grid.h.step);
    const y = clampSnap(roi.y, 0, grid.v.max - h, grid.v.step);
    return { x, y, w, h };
  }

  /** Set the full ROI (clamped to the merged grid), fanning out to peers when linked. */
  patch(roi: SensorROI): Promise<unknown> {
    const resolved = this.resolve(roi);
    return this.#dispatch((m) => m.#apply(resolved));
  }

  /** Merge a partial ROI over the current value, then patch. No-op until ROI hydrates. */
  patchDim(partial: Partial<SensorROI>): Promise<unknown> {
    const current = this.value;
    if (!current) return Promise.resolve();
    return this.patch({ ...current, ...partial });
  }

  /** Recenter each camera's ROI within its own sensor (keeps width/height). */
  center(): Promise<unknown> {
    return this.#dispatch((m) => {
      const roi = m.value;
      const sensor = m.sensor;
      if (!roi || !sensor) return undefined;
      return m.#apply({ ...roi, x: Math.floor((sensor.x - roi.w) / 2), y: Math.floor((sensor.y - roi.h) / 2) });
    });
  }

  /** Reset each camera's ROI to its own full sensor. */
  reset(): Promise<unknown> {
    return this.#dispatch((m) => {
      const sensor = m.sensor;
      if (!sensor) return undefined;
      return m.#apply({ x: 0, y: 0, w: sensor.x, h: sensor.y });
    });
  }

  /** Push an ROI to this camera's hardware via the update_roi command; backend snaps to grid. */
  #apply(roi: SensorROI): Promise<unknown> {
    return this.#camera.runCommand('update_roi', [], { roi });
  }

  /** Run `fn` on self, or on every peer when linked; resolves once all writes settle. */
  #dispatch(fn: (m: RoiModel) => Promise<unknown> | undefined): Promise<unknown> {
    const targets = this.group ? [...this.group.members] : [this];
    return Promise.all(targets.map((m) => fn(m)));
  }
}

export interface StreamInfoData {
  frame_index: number;
  frame_rate_fps: number;
  data_rate_mbs: number;
  dropped_frames: number;
  input_buffer_size: number;
  output_buffer_size: number;
  payload_mbs?: number;
}

export class CameraHandle extends DeviceHandle {
  exposure = $derived.by(() => this.typedProp('exposure_time_ms', NumericModel));
  frameRate = $derived.by(() => this.typedProp('frame_rate_hz', NumericModel));
  frameSizeMb = $derived.by(() => this.typedProp('frame_size_mb', NumericModel));

  pixelFormat = $derived.by((): EnumeratedModel<string> | undefined => {
    const m = this.getProp('pixel_format')?.model;
    return m instanceof EnumeratedModel ? (m as EnumeratedModel<string>) : undefined;
  });

  binning = $derived.by((): EnumeratedModel<number> | undefined => {
    const m = this.getProp('binning')?.model;
    return m instanceof EnumeratedModel ? (m as EnumeratedModel<number>) : undefined;
  });

  /** The sole ROI entry point: reads (`roi.value`, `roi.grid`), writes, and cross-camera linking. */
  roi = new RoiModel(this);

  streamInfo = $derived.by<StreamInfoData | undefined>(() => {
    const v = this.getProp('stream_info')?.value;
    return v && typeof v === 'object' ? (v as StreamInfoData) : undefined;
  });

  /** Fraction of the capture buffer that is filled (0–1), or null when the driver doesn't report usable buffer sizes. */
  bufferFill = $derived.by<number | null>(() => {
    const info = this.streamInfo;
    if (!info || info.input_buffer_size < 0 || info.output_buffer_size < 0) return null;
    const total = info.input_buffer_size + info.output_buffer_size;
    return total > 0 ? info.output_buffer_size / total : null;
  });

  mode = $derived.by<CameraMode | undefined>(() => {
    const v = this.getProp('mode')?.value;
    return v === 'IDLE' || v === 'PREVIEW' || v === 'ACQUISITION' ? v : undefined;
  });

  sensorSizePx = $derived.by<Vec2D | null>(() => parseVec2D(this.getProp('sensor_size_px')?.value));
  pixelSizeUm = $derived.by<Vec2D | null>(() => parseVec2D(this.getProp('pixel_size_um')?.value));
  frameSizePx = $derived.by<Vec2D | null>(() => parseVec2D(this.getProp('frame_size_px')?.value));
  frameAreaUm = $derived.by<Vec2D | null>(() => parseVec2D(this.getProp('frame_area_um')?.value));
}

/** Instantiate the typed handle matching a device's introspected `interface.type`. */
export function createDevice(client: Client, snapshot: DeviceSnapshot): DeviceHandle {
  switch (snapshot.interface?.type) {
    case 'camera':
      return new CameraHandle(client, snapshot);
    case 'laser':
      return new LaserHandle(client, snapshot);
    case 'continuous_axis':
      return new AxisHandle(client, snapshot);
    case 'discrete_axis':
      return new DiscreteAxisHandle(client, snapshot);
    case 'analog_output':
      return new AnalogOutHandle(client, snapshot);
    default:
      return new DeviceHandle(client, snapshot);
  }
}
