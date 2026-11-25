import type { Client } from './client.svelte';
import type { Topics } from './topics.svelte';
import type {
  AreaROI,
  CameraSensor,
  ControlMode,
  DeviceInterface,
  OperationParam,
  PropResults,
  PropValue,
  ROIGrid,
  StreamInfo
} from './types';

interface ParamSchema {
  type?: string | string[];
  default?: unknown;
  enum?: unknown[];
  anyOf?: ParamSchema[];
  $ref?: string;
  $defs?: Record<string, ParamSchema>;
  properties?: Record<string, ParamSchema>;
  required?: string[];
}

/**
 * A device of the open instrument, read from the feed topics `instrument.devices.<id>.*`. Writes go through the
 * instrument's routes, which decide whether the device may be used now.
 */
export class Device {
  readonly id: string;
  readonly #client: Client;
  readonly #topics: Topics;
  readonly #base: string;

  constructor(client: Client, topics: Topics, base: string, id: string) {
    this.id = id;
    this.#client = client;
    this.#topics = topics;
    this.#base = `${base}/devices/${encodeURIComponent(id)}`;
  }

  /** Undefined until the feed sends it. */
  get interface(): DeviceInterface | undefined {
    return this.#topics.get<DeviceInterface>('interface');
  }

  get propNames(): string[] {
    return this.#topics.names('props');
  }

  /** The class of the device's kind, or a plain Device for a kind with no class. */
  static of(client: Client, topics: Topics, base: string, id: string): Device {
    const kinds: Record<string, typeof Device> = {
      laser: Laser,
      modulator: Modulator,
      shutter: Shutter,
      linear_axis: LinearAxis,
      discrete_axis: DiscreteAxis,
      area_camera: AreaCamera
    };
    const kind = topics.get<DeviceInterface>('interface')?.kind ?? '';
    return new (kinds[kind] ?? Device)(client, topics, base, id);
  }

  prop<T>(name: string): PropValue<T> | undefined {
    return this.#topics.get<PropValue<T>>(`props.${name}`);
  }

  value<T>(name: string): T | undefined {
    return this.prop<T>(name)?.value ?? undefined;
  }

  /** Such as `mW`, or an empty string. */
  unit(name: string): string {
    return this.interface?.props[name]?.units ?? '';
  }

  /** The station refuses all of them when it refuses 1. */
  set(properties: Record<string, unknown>): Promise<PropResults> {
    return this.#client.patch<PropResults>(this.#base, properties);
  }

  /** In JSON Schema order. A nullable argument takes its other type, so `int | None` is an integer. */
  params(name: string): OperationParam[] {
    const root = (this.interface?.operations[name]?.params ?? {}) as ParamSchema;
    return Device.#fields(root, root, 0);
  }

  /** `depth` stops a recursive schema. */
  static #fields(schema: ParamSchema, root: ParamSchema, depth: number): OperationParam[] {
    const required = new Set(schema.required ?? []);
    return Object.entries(schema.properties ?? {}).map(([name, raw]): OperationParam => {
      const plain = Device.#notNull(raw, root);
      const named = Array.isArray(plain.type) ? plain.type.find((type) => type !== 'null') : plain.type;
      const options = plain.enum?.filter((option) => typeof option === 'string' || typeof option === 'number');
      const param = { name, required: required.has(name), default: plain.default };
      if (options?.length) return { ...param, type: 'string', options };
      if (named === 'integer' || named === 'number' || named === 'boolean' || named === 'string') {
        return { ...param, type: named };
      }
      if (plain.properties && depth < Device.#DEPTH) {
        return { ...param, type: 'object', fields: Device.#fields(plain, root, depth + 1) };
      }
      return { ...param, type: 'other' };
    });
  }

  static readonly #DEPTH = 8;

  static #resolved(schema: ParamSchema, root: ParamSchema): ParamSchema {
    const name = schema.$ref?.split('/').pop();
    return name && root.$defs?.[name] ? { ...root.$defs[name], ...schema, $ref: undefined } : schema;
  }

  static #notNull(schema: ParamSchema, root: ParamSchema): ParamSchema {
    const resolved = Device.#resolved(schema, root);
    const branch = resolved.anyOf
      ?.map((option) => Device.#resolved(option, root))
      .find((option) => option.type !== 'null');
    return branch ? { ...branch, default: resolved.default } : resolved;
  }

  run<T = unknown>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    return this.#client.post<T>(`${this.#base}:${encodeURIComponent(name)}`, args);
  }
}

/** A laser or a modulator. Power is the setpoint, not a measurement, in the device's own unit. */
export class Dimmable extends Device {
  get power(): number | undefined {
    return this.value<number>('power');
  }

  /** Both ends are equal when the power is fixed. */
  get powerRange(): [number, number] | undefined {
    return this.value<[number, number]>('power_range');
  }

  get powerUnit(): string {
    return this.unit('power');
  }

  get isOn(): boolean {
    return this.value<boolean>('is_on') ?? false;
  }

  get controlMode(): ControlMode | undefined {
    return this.value<ControlMode>('control_mode');
  }
}

export class Laser extends Dimmable {
  /** In nm. */
  get wavelength(): number | undefined {
    return this.value<number>('wavelength');
  }
}

/** Power in %. */
export class Modulator extends Dimmable {}

export class Shutter extends Device {
  get isOpen(): boolean {
    return this.value<boolean>('is_open') ?? false;
  }
}

export class LinearAxis extends Device {
  get position(): number | undefined {
    return this.value<number>('position');
  }

  get limits(): [number, number] | undefined {
    return this.value<[number, number]>('limits');
  }

  get positionUnit(): string {
    return this.unit('position');
  }

  get isMoving(): boolean {
    return this.value<boolean>('is_moving') ?? false;
  }

  moveTo(position: number): Promise<void> {
    return this.run('move_to', { position });
  }

  halt(): Promise<void> {
    return this.run('halt');
  }
}

/** An axis with named positions, such as a filter wheel or a light router. */
export class DiscreteAxis extends Device {
  /** In slot order; unnamed slots are left out. */
  get labels(): string[] {
    const labels = this.value<Record<string, string>>('labels') ?? {};
    return Object.keys(labels)
      .sort((a, b) => Number(a) - Number(b))
      .map((slot) => labels[slot]);
  }

  /** Undefined between positions or at an unnamed slot. */
  get position(): string | undefined {
    return this.#state?.position ?? undefined;
  }

  get isMoving(): boolean {
    return this.#state?.is_moving ?? false;
  }

  moveTo(position: string): Promise<void> {
    return this.run('move_to', { position });
  }

  halt(): Promise<void> {
    return this.run('halt');
  }

  get #state():
    | { position: string | null; slot: number | null; target: number | null; is_moving: boolean }
    | undefined {
    return this.value('state');
  }
}

export class AreaCamera extends Device {
  /** Undefined while no frames are sent. */
  get streamInfo(): StreamInfo | undefined {
    return this.value<StreamInfo>('stream_info');
  }

  get sensor(): CameraSensor | undefined {
    return this.value<CameraSensor>('sensor');
  }

  get roi(): AreaROI | undefined {
    return this.value<AreaROI>('roi');
  }

  get roiGrid(): ROIGrid | undefined {
    return this.value<ROIGrid>('roi_grid');
  }
}
