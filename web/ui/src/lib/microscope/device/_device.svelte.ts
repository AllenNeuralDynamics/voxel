import type { AOSignals } from '$lib/protocol/session';
import type { DeviceInterface } from '$lib/protocol/device';
import {
  BoolModel,
  createPropModel,
  EnumeratedModel,
  NumericModel,
  type AnyPropModel,
  type PropSnapshot
} from '$lib/prop.svelte';
import { parseVec2D, type Vec2D } from '$lib/utils/vec';
import type { SensorROI } from '$lib/protocol/profile';
import { wavelengthToColor } from '$lib/utils';
import { SvelteSet } from 'svelte/reactivity';

const _warnedTypedPropKeys = new SvelteSet<string>();

export interface DeviceCallbacks {
  patch: (propName: string, value: unknown) => void;
  execute: (command: string, args?: unknown[], kwargs?: Record<string, unknown>) => Promise<unknown>;
}

export class Device {
  id: string;
  connected = $state(false);
  error = $state<string | undefined>(undefined);
  interface = $state<DeviceInterface | undefined>(undefined);
  props = $state<Record<string, AnyPropModel>>({});

  #patch: DeviceCallbacks['patch'];
  #execute: DeviceCallbacks['execute'];

  constructor(id: string, callbacks: DeviceCallbacks) {
    this.id = id;
    this.#patch = callbacks.patch;
    this.#execute = callbacks.execute;
  }

  getProp(name: string): AnyPropModel | undefined {
    return this.props[name];
  }

  /** Read a property and assert its model type; warns once per (deviceId, propName, kind) on mismatch. */
  protected typedProp<T extends AnyPropModel>(name: string, ctor: new (...args: never[]) => T): T | undefined {
    const p = this.getProp(name);
    if (p === undefined) return undefined;
    if (p instanceof ctor) return p;
    const key = `${this.id}.${name}.${p.constructor.name}`;
    if (!_warnedTypedPropKeys.has(key)) {
      _warnedTypedPropKeys.add(key);
      console.warn(
        `[${this.constructor.name} ${this.id}] expected ${ctor.name} for '${name}', got ${p.constructor.name}`
      );
    }
    return undefined;
  }

  upsertProp(name: string, snapshot: PropSnapshot<unknown>): void {
    const existing = this.props[name];
    if (existing) {
      existing.update(snapshot);
    } else {
      this.props[name] = createPropModel(snapshot, (v) => this.#patch(name, v));
    }
  }

  execute(command: string, args?: unknown[], kwargs?: Record<string, unknown>): Promise<unknown> {
    return this.#execute(command, args, kwargs);
  }
}

export type AOState = 'fresh' | 'ready' | 'running';

export class AnalogOut extends Device {
  /** Currently loaded signals; `null` when fresh or after a failed load. */
  loaded = $derived.by<AOSignals | null>(() => {
    const v = this.getProp('loaded')?.value;
    return (v ?? null) as AOSignals | null;
  });

  state = $derived.by<AOState>(() => {
    const v = this.getProp('state')?.value;
    return (typeof v === 'string' ? v : 'fresh') as AOState;
  });

  voltageRange = $derived.by<{ min: number; max: number } | null>(() => {
    const v = this.getProp('voltage_range')?.value;
    if (v && typeof v === 'object' && 'min' in v && 'max' in v) {
      return v as { min: number; max: number };
    }
    return null;
  });

  isRunning = $derived(this.state === 'running');
}

export class Axis extends Device {
  position = $derived.by(() => this.typedProp('position', NumericModel));
  lowerLimit = $derived.by(() => this.typedProp('lower_limit', NumericModel));
  upperLimit = $derived.by(() => this.typedProp('upper_limit', NumericModel));
  isMoving = $derived.by(() => this.typedProp('is_moving', BoolModel));

  range = $derived((this.upperLimit?.value ?? 100) - (this.lowerLimit?.value ?? 0));

  /** Move to absolute position, clamped to soft limits. */
  move(position: number): Promise<unknown> {
    const lower = this.lowerLimit?.value ?? 0;
    const upper = this.upperLimit?.value ?? 100;
    const clamped = Math.max(lower, Math.min(upper, position));
    return this.execute('move_abs', [clamped], { wait: false });
  }

  halt(): Promise<unknown> {
    return this.execute('halt');
  }
}

export class Laser extends Device {
  static readonly POWER_HISTORY_MAX = 600;

  powerHistory = $state<number[]>([]);

  /** Measured power (`value`) + commanded setpoint (`target`); writes go to the setpoint. */
  power = $derived.by(() => this.typedProp('power', NumericModel));
  isEnabled = $derived.by(() => this.typedProp('is_enabled', BoolModel));
  wavelength = $derived.by(() => this.typedProp('wavelength', NumericModel));
  temperature = $derived.by(() => this.typedProp('temperature_c', NumericModel));

  color = $derived.by((): string | undefined => {
    const wl = this.wavelength?.value;
    return typeof wl === 'number' ? wavelengthToColor(wl) : undefined;
  });

  hasHistory = $derived(this.powerHistory.length > 1);
  maxPower = $derived(this.power?.max ?? 100);

  enable(): Promise<unknown> {
    return this.execute('enable');
  }

  disable(): Promise<unknown> {
    return this.execute('disable');
  }

  toggle(): Promise<unknown> {
    return this.isEnabled?.value ? this.disable() : this.enable();
  }

  /** Append the current measured power to history, trimming to `POWER_HISTORY_MAX`. */
  recordPower(): void {
    const v = this.power?.value;
    if (typeof v !== 'number') return;
    if (this.powerHistory.length >= Laser.POWER_HISTORY_MAX) {
      this.powerHistory = [...this.powerHistory.slice(1), v];
    } else {
      this.powerHistory = [...this.powerHistory, v];
    }
  }
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

export interface StreamInfoData {
  frame_index: number;
  frame_rate_fps: number;
  data_rate_mbs: number;
  dropped_frames: number;
  input_buffer_size: number;
  output_buffer_size: number;
  payload_mbs?: number;
}

export class Camera extends Device {
  exposure = $derived.by(() => this.typedProp('exposure_time_ms', NumericModel));
  frameRate = $derived.by(() => this.typedProp('frame_rate_hz', NumericModel));
  frameSizeMb = $derived.by(() => this.typedProp('frame_size_mb', NumericModel));

  pixelFormat = $derived.by((): EnumeratedModel<string> | undefined => {
    const p = this.getProp('pixel_format');
    return p instanceof EnumeratedModel ? (p as EnumeratedModel<string>) : undefined;
  });

  binning = $derived.by((): EnumeratedModel<number> | undefined => {
    const p = this.getProp('binning');
    return p instanceof EnumeratedModel ? (p as EnumeratedModel<number>) : undefined;
  });

  roi = $derived.by((): SensorROI | undefined => {
    const v = this.getProp('roi')?.value;
    return v && typeof v === 'object' ? (v as SensorROI) : undefined;
  });

  roiGrid = $derived.by((): ROIGrid | undefined => {
    const v = this.getProp('roi_grid')?.value;
    return v && typeof v === 'object' ? (v as ROIGrid) : undefined;
  });

  streamInfo = $derived.by((): StreamInfoData | undefined => {
    const v = this.getProp('stream_info')?.value;
    return v && typeof v === 'object' ? (v as StreamInfoData) : undefined;
  });

  mode = $derived.by((): CameraMode | undefined => {
    const v = this.getProp('mode')?.value;
    return v === 'IDLE' || v === 'PREVIEW' || v === 'ACQUISITION' ? v : undefined;
  });

  sensorSizePx = $derived.by((): Vec2D | null => parseVec2D(this.getProp('sensor_size_px')?.value));
  pixelSizeUm = $derived.by((): Vec2D | null => parseVec2D(this.getProp('pixel_size_um')?.value));
  frameSizePx = $derived.by((): Vec2D | null => parseVec2D(this.getProp('frame_size_px')?.value));
  frameAreaUm = $derived.by((): Vec2D | null => parseVec2D(this.getProp('frame_area_um')?.value));

  /** Update the active sensor ROI. */
  updateRoi(roi: SensorROI): Promise<unknown> {
    return this.execute('update_roi', [], { roi });
  }
}
