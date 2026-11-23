/** 1 device of the open instrument. */
import type { Client } from './client.svelte';
import type { Topics } from './topics.svelte';
import type { DeviceInterface, PropResults } from './types';

/**
 * A device of the open instrument: its interface and its properties, read from the feed topics
 * `instrument.devices.<id>.*`. Reading 1 property tracks only that property. Writes go through the instrument's
 * routes, which decide whether the device may be used now.
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

  /** The last value of the property `name`, as the feed sends it. */
  prop<T>(name: string): T | undefined {
    return this.#topics.get<T>(`props.${name}`);
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
