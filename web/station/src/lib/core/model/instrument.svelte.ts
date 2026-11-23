/** The station's open instrument. */
import { TaskChain } from '$lib/core/utils/task-chain.svelte';

import type { Client } from './client.svelte';
import { Device } from './device.svelte';
import type { Topics } from './topics.svelte';
import type { Alert, HttpInstrumentInterface, InstrumentConfig } from './types';

/**
 * The open instrument of 1 session: its state and devices, read from the feed topics `instrument.*`, and the steps that
 * change it, sent to `<station>/instrument`. An edit of the instrument's state goes through `edits`, in order; a step
 * that drives the hardware, such as starting the preview, is sent at once.
 */
export class Instrument {
  readonly edits = new TaskChain();
  readonly #client: Client;
  readonly #topics: Topics;
  readonly #base: string;
  readonly #devices = new Map<string, Device>();

  /** What a client can ask this instrument and how it reaches each operation, or undefined until it loads. */
  interface = $state.raw<HttpInstrumentInterface | undefined>(undefined);

  constructor(client: Client, topics: Topics, base: string) {
    this.#client = client;
    this.#topics = topics;
    this.#base = base;
    // The interface stays the same while the session is open, so 1 load is enough.
    void this.#client.get<HttpInstrumentInterface>(`${base}/interface`).then((loaded) => (this.interface = loaded));
  }

  /**
   * Runs the operation `name` at its route. A `{name}` in the path takes that argument; a `GET` sends the others as
   * query parameters, with a list as 1 parameter per item, and any other method as the body.
   */
  async call<T = unknown>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    const operation = this.interface?.operations[name];
    if (!operation) throw new Error(`The instrument has no operation '${name}'.`);
    const rest = { ...args };
    const path = operation.path.replace(/\{(\w+)\}/g, (_, key: string) => {
      const value = rest[key];
      delete rest[key];
      return encodeURIComponent(String(value));
    });
    const at = `${this.#base}${path}`;
    switch (operation.method) {
      case 'GET': {
        const query = new URLSearchParams();
        for (const [key, value] of Object.entries(rest)) {
          for (const item of Array.isArray(value) ? value : [value]) query.append(key, String(item));
        }
        const search = query.toString();
        return this.#client.get<T>(search ? `${at}?${search}` : at);
      }
      case 'POST':
        return this.#client.post<T>(at, rest);
      case 'PATCH':
        return this.#client.patch<T>(at, rest);
      case 'DELETE':
        return this.#client.del<T>(at);
    }
  }

  get config(): InstrumentConfig | undefined {
    return this.#topics.get<InstrumentConfig>('config');
  }

  /** The id of the profile in use, or undefined. */
  get activeProfile(): string | undefined {
    return this.#topics.get<string>('active_profile');
  }

  /** The name of the operation that runs now, or null. */
  get operation(): string | null {
    return this.#topics.get<string>('operation') ?? null;
  }

  /** What is wrong now. */
  get alerts(): Alert[] {
    return this.#topics.get<Alert[]>('alerts') ?? [];
  }

  /** The ids of the saved profiles. */
  get profileIds(): string[] {
    return this.#topics.names('state.profiles');
  }

  /** The profile `id`, or undefined. */
  profile<T = Record<string, unknown>>(id: string): T | undefined {
    return this.#topics.get<T>(`state.profiles.${id}`);
  }

  /** A Device for each device id that the feed sends. A Device is made once per id and kept while the id stays. */
  readonly devices: Device[] = $derived.by(() => {
    const ids = this.#topics.names('devices');
    for (const id of this.#devices.keys()) if (!ids.includes(id)) this.#devices.delete(id);
    return ids.map((id) => {
      let device = this.#devices.get(id);
      if (!device) {
        device = new Device(this.#client, this.#topics.scope(`devices.${id}`), this.#base, id);
        this.#devices.set(id, device);
      }
      return device;
    });
  });

  /** The device `id`, or undefined. */
  device(id: string): Device | undefined {
    return this.devices.find((device) => device.id === id);
  }

  selectProfile(id: string): Promise<void> {
    return this.edits.run(() => this.call('select_profile', { profile_id: id }));
  }

  undo(): Promise<void> {
    return this.edits.run(() => this.call('undo'));
  }

  redo(): Promise<void> {
    return this.edits.run(() => this.call('redo'));
  }

  startPreview(): Promise<void> {
    return this.call('start_preview');
  }

  stopPreview(): Promise<void> {
    return this.call('stop_preview');
  }

  /** Stops what the instrument is doing now, such as the preview or an acquisition. */
  stop(): Promise<void> {
    return this.call('stop');
  }

  /** Refuses every edit from now on, once the session ends. */
  dispose(): void {
    this.edits.dispose();
  }
}
