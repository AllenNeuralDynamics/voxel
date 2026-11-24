/** The devices of the open instrument: any device, and typed classes for the kinds that the pages read by name. */
import type { Client } from './client.svelte';
import type { Topics } from './topics.svelte';
import type { ControlMode, DeviceInterface, PropResults, PropValue, StreamInfo } from './types';

/**
 * A device of the open instrument: its interface and its properties, read from the feed topics
 * `instrument.devices.<id>.*`. Reading 1 property tracks only that property. Writes go through the instrument's
 * routes, which decide whether the device may be used now. `Device.of` gives the class of a device's kind.
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

  /** The device's kind, properties and operations, or undefined until the feed sends it. */
  get interface(): DeviceInterface | undefined {
    return this.#topics.get<DeviceInterface>('interface');
  }

  /** The names of the properties that the feed sends. */
  get propNames(): string[] {
    return this.#topics.names('props');
  }

  /** A device as the class of its kind, or as a plain Device for a kind with no class. */
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

  /** The last report of the property `name`: its value with its limits, step and choices. */
  prop<T>(name: string): PropValue<T> | undefined {
    return this.#topics.get<PropValue<T>>(`props.${name}`);
  }

  /** The last value of the property `name`, or undefined when the device has not reported one. */
  value<T>(name: string): T | undefined {
    return this.prop<T>(name)?.value ?? undefined;
  }

  /** The unit of the property `name`, such as `mW`, or an empty string. */
  unit(name: string): string {
    return this.interface?.props[name]?.units ?? '';
  }

  /** Sets properties. The station refuses all of them when it refuses 1. */
  set(properties: Record<string, unknown>): Promise<PropResults> {
    return this.#client.patch<PropResults>(this.#base, properties);
  }

  /** Runs the operation `name` with its arguments by name. */
  run<T = unknown>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    return this.#client.post<T>(`${this.#base}:${encodeURIComponent(name)}`, args);
  }
}

/** A laser or a modulator: its power, as it is set and not as measured, in the device's own unit. */
export class Dimmable extends Device {
  get power(): number | undefined {
    return this.value<number>('power');
  }

  /** The lowest and the highest power it can do. Both are the same when its power is fixed. */
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

/** A laser: it makes light at 1 wavelength. */
export class Laser extends Dimmable {
  /** In nm. */
  get wavelength(): number | undefined {
    return this.value<number>('wavelength');
  }
}

/** A modulator: it lets a part of the light through, in %. */
export class Modulator extends Dimmable {}

/** A shutter: it lets the light through, or blocks it. */
export class Shutter extends Device {
  get isOpen(): boolean {
    return this.value<boolean>('is_open') ?? false;
  }
}

/** An axis that moves along a line, such as a focus stage. */
export class LinearAxis extends Device {
  get position(): number | undefined {
    return this.value<number>('position');
  }

  /** The lowest and the highest position it can go to. */
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

  /** Stops a move. */
  halt(): Promise<void> {
    return this.run('halt');
  }
}

/** An axis with a few named positions, such as a filter wheel or a device that sends the light 1 of several ways. */
export class DiscreteAxis extends Device {
  /** The names of its positions, in slot order. A slot with no name is left out. */
  get labels(): string[] {
    const labels = this.value<Record<string, string>>('labels') ?? {};
    return Object.keys(labels)
      .sort((a, b) => Number(a) - Number(b))
      .map((slot) => labels[slot]);
  }

  /** The name of the position it is at, or undefined between positions or at a slot with no name. */
  get position(): string | undefined {
    return this.#state?.position ?? undefined;
  }

  get isMoving(): boolean {
    return this.#state?.is_moving ?? false;
  }

  /** Moves to the position named `position`. */
  moveTo(position: string): Promise<void> {
    return this.run('move_to', { position });
  }

  /** Stops a move. */
  halt(): Promise<void> {
    return this.run('halt');
  }

  get #state():
    | { position: string | null; slot: number | null; target: number | null; is_moving: boolean }
    | undefined {
    return this.value('state');
  }
}

/** A camera with an area sensor. */
export class AreaCamera extends Device {
  /** How its stream runs, or undefined while it sends no frames. */
  get streamInfo(): StreamInfo | undefined {
    return this.value<StreamInfo>('stream_info');
  }
}
