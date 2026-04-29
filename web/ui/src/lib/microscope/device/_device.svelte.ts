import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import type { AOSignals } from '$lib/config';
import {
  type AnyPropModel,
  BoolModel,
  createPropModel,
  EnumeratedModel,
  NumericModel,
  Prop,
  type PropertyInfo,
  type PropSnapshot
} from '$lib/prop';
import type { SensorROI } from '$lib/protocol/profile';
import { wavelengthToColor } from '$lib/utils';
import { parseVec2D, type Vec2D } from '$lib/utils/vec';

const _warnedTypedPropKeys = new SvelteSet<string>();

export interface ParamInfo {
  dtype: string;
  required: boolean;
  default?: unknown | null;
  kind: 'regular' | 'var_positional' | 'var_keyword';
  options?: string[] | null;
}

export interface CommandInfo {
  name: string;
  label: string;
  desc?: string | null;
  params: Record<string, ParamInfo>;
}

export interface DeviceInterface {
  uid: string;
  type: string;
  commands: Record<string, CommandInfo>;
  properties: Record<string, PropertyInfo>;
}

export interface DeviceSnapshot {
  id: string;
  connected: boolean;
  interface?: DeviceInterface;
  error?: string;
}

export interface DeviceHooks {
  getSaved?: (propName: string) => unknown;
  onPatch: (propName: string, value: unknown) => void;
  onExecute: (command: string, args?: unknown[], kwargs?: Record<string, unknown>) => Promise<unknown>;
}

export class Device {
  id: string;
  connected = $state(false);
  error = $state<string | undefined>(undefined);
  interface = $state<DeviceInterface | undefined>(undefined);
  props = new SvelteMap<string, Prop>();

  #hooks: DeviceHooks;

  constructor(id: string, hooks: DeviceHooks) {
    this.id = id;
    this.#hooks = hooks;
  }

  applySnapshot(snapshot: DeviceSnapshot): void {
    this.connected = snapshot.connected;
    this.interface = snapshot.interface;
    this.error = snapshot.error;
  }

  getProp(name: string): Prop | undefined {
    return this.props.get(name);
  }

  /** Read a property's model and assert its type; warns once per (deviceId, propName, kind) on mismatch. */
  protected typedProp<T extends AnyPropModel>(name: string, ctor: new (...args: never[]) => T): T | undefined {
    const model = this.getProp(name)?.model;
    if (model === undefined) return undefined;
    if (model instanceof ctor) return model;
    const key = `${this.id}.${name}.${model.constructor.name}`;
    if (!_warnedTypedPropKeys.has(key)) {
      _warnedTypedPropKeys.add(key);
      console.warn(
        `[${this.constructor.name} ${this.id}] expected ${ctor.name} for '${name}', got ${model.constructor.name}`
      );
    }
    return undefined;
  }

  upsertProp(name: string, snapshot: PropSnapshot<unknown>): void {
    const existing = this.props.get(name);
    if (existing) {
      existing.model.update(snapshot);
      return;
    }
    const info = this.interface?.properties?.[name];
    if (!info) {
      console.warn(`[${this.constructor.name} ${this.id}] no interface entry for property '${name}'`);
      return;
    }
    const model = createPropModel(snapshot, (v) => this.#hooks.onPatch(name, v));
    const getSaved = this.#hooks.getSaved ? () => this.#hooks.getSaved!(name) : undefined;
    this.props.set(name, new Prop(model, info, getSaved));
  }

  execute(command: string, args?: unknown[], kwargs?: Record<string, unknown>): Promise<unknown> {
    return this.#hooks.onExecute(command, args, kwargs);
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
    const m = this.getProp('pixel_format')?.model;
    return m instanceof EnumeratedModel ? (m as EnumeratedModel<string>) : undefined;
  });

  binning = $derived.by((): EnumeratedModel<number> | undefined => {
    const m = this.getProp('binning')?.model;
    return m instanceof EnumeratedModel ? (m as EnumeratedModel<number>) : undefined;
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
