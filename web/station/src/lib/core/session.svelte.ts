import { TaskChain } from '$lib/core/utils/task-chain.svelte';
import { ObjectDiff } from '@voxel/kit/object-diff';

import type { Client } from './client.svelte';
import { Device, Laser, Modulator, Shutter } from './device.svelte';
import type { Instrument } from './instrument.svelte';
import type { Timeline, TuningField } from './signals';
import type { Topics } from './topics.svelte';
import type {
  ActivityInfo,
  Alert,
  HistoryState,
  HttpInstrumentInterface,
  KeyPath,
  PowerMode,
  ProfileFields
} from './types';

/** A laser with the modulators and shutters only its light passes. */
export interface Beam {
  source: Laser;
  own: (Modulator | Shutter)[];
  reaches: boolean;
  blockedBy: Modulator | Shutter | undefined;
}

/**
 * The running instrument's session, read from `instrument.*` topics. State edits go through `edits` in order; hardware
 * steps, such as turning the lasers off, are sent at once.
 */
export class InstrumentSession<I extends Instrument = Instrument> {
  /** New each time an instrument opens. */
  readonly id: string;
  readonly instrument: I;
  readonly edits = new TaskChain();
  readonly #client: Client;
  readonly #topics: Topics;
  readonly #base: string;
  readonly #devices = new Map<string, Device>();

  /** Undefined until loaded. */
  interface = $state.raw<HttpInstrumentInterface | undefined>(undefined);

  constructor(client: Client, topics: Topics, base: string, id: string, instrument: I) {
    this.id = id;
    this.instrument = instrument;
    this.#client = client;
    this.#topics = topics;
    this.#base = base;
    // The interface is fixed for the session's lifetime.
    void this.#client.get<HttpInstrumentInterface>(`${base}/interface`).then((loaded) => (this.interface = loaded));
  }

  /**
   * A `{name}` in the path takes that argument. `GET` sends the rest as query parameters (a list as 1 per item); other
   * methods send them as the body.
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

  protected view<T>(name: string): T | undefined {
    return this.#topics.get<T>(name);
  }

  get activeProfile(): string | undefined {
    return this.#topics.get<string>('active_profile');
  }

  get operation(): string | null {
    return this.#topics.get<string>('operation') ?? null;
  }

  get powerMode(): PowerMode | undefined {
    return this.#topics.get<PowerMode>('power_mode');
  }

  get alerts(): Alert[] {
    return this.#topics.get<Alert[]>('alerts') ?? [];
  }

  get activities(): ActivityInfo[] {
    return this.#topics.get<ActivityInfo[]>('activities') ?? [];
  }

  activity<T extends ActivityInfo = ActivityInfo>(kind: T['kind']): T | undefined {
    return this.activities.find((activity) => activity.kind === kind) as T | undefined;
  }

  /** Undo and redo of the saved state, not past runs. */
  get history(): HistoryState {
    return this.#topics.get<HistoryState>('history') ?? { undo_label: null, redo_label: null };
  }

  /** A device is built once the feed has its interface, and kept while its id stays. */
  readonly devices: Device[] = $derived.by(() => {
    const ids = this.#topics.names('devices');
    for (const id of this.#devices.keys()) if (!ids.includes(id)) this.#devices.delete(id);
    const devices: Device[] = [];
    for (const id of ids) {
      const topics = this.#topics.scope(`devices.${id}`);
      if (!this.#devices.has(id) && topics.has('interface')) {
        this.#devices.set(id, Device.of(this.#client, topics, this.#base, id));
      }
      const device = this.#devices.get(id);
      if (device) devices.push(device);
    }
    return devices;
  });

  /**
   * In wavelength order. The light reaches the sample when the laser is on and, on 1 of its paths, every modulator is
   * on and every shutter open; otherwise `blockedBy` is the first device that stops it.
   */
  readonly beams: Beam[] = $derived.by(() => {
    const gates = new Map(
      this.devices.flatMap((device): [string, Modulator | Shutter][] =>
        device instanceof Modulator || device instanceof Shutter ? [[device.id, device]] : []
      )
    );
    const stops = (gate: Modulator | Shutter): boolean => !(gate instanceof Shutter ? gate.isOpen : gate.isOn);
    return this.devicesOf(Laser)
      .toSorted((a, b) => (a.wavelength ?? 0) - (b.wavelength ?? 0))
      .map((source) => {
        const ways = this.instrument.lightPaths
          .from(source.id)
          .map((path) => path.nodes.flatMap((node) => gates.get(node) ?? []));
        const blockers = ways.map((way) => way.find(stops));
        const open = ways.length === 0 || blockers.some((blocker) => blocker === undefined);
        const own = [...new Set(ways.flat())].filter(
          (gate) => this.instrument.lightPaths.serves(gate.id)?.ends.length === 1
        );
        return { source, own, reaches: source.isOn && open, blockedBy: source.isOn && !open ? blockers[0] : undefined };
      });
  });

  /** Modulators and shutters passed by more than 1 laser, in path order. */
  readonly sharedGates: (Modulator | Shutter)[] = $derived.by(() =>
    this.devices.filter(
      (device): device is Modulator | Shutter =>
        (device instanceof Modulator || device instanceof Shutter) &&
        (this.instrument.lightPaths.serves(device.id)?.ends.length ?? 0) > 1
    )
  );

  devicesOf<T extends Device>(type: new (...args: never[]) => T): T[] {
    return this.devices.filter((device): device is T => device instanceof type);
  }

  /** With `type`, also undefined when the device is not of that class. */
  device(id: string): Device | undefined;
  device<T extends Device>(id: string, type: new (...args: never[]) => T): T | undefined;
  device<T extends Device>(id: string, type?: new (...args: never[]) => T): Device | T | undefined {
    const device = this.devices.find((found) => found.id === id);
    return !type || device instanceof type ? device : undefined;
  }

  selectProfile(id: string): Promise<void> {
    return this.edits.run(() => this.call('select_profile', { profile_id: id }));
  }

  /** Applied as 1 edit. */
  updateProfile(id: string, fields: ProfileFields): Promise<void> {
    return this.edits.run(() => this.call('update_profile', { profile_id: id, ...fields }));
  }

  /**
   * Also saved into the active profile. A timeline that does not fit is refused before the generator changes. Not
   * undoable.
   */
  setGeneratorTimeline(generator: string, timeline: Timeline): Promise<void> {
    return this.edits.run(() => this.call('set_generator_timeline', { generator, timeline }));
  }

  /** `value` is in the fixed unit of `field`. Returns the value the instrument took. Not undoable. */
  setTuningKnob(generator: string, wire: string, field: TuningField, value: number): Promise<number> {
    return this.edits.run(() => this.call<number>('set_tuning_knob', { generator, wire, field, value }));
  }

  /**
   * Applied as 1 edit. Keys missing from the defaults are left as they are. No paths restores every defaultable field.
   * Refused as a whole when the result would have a problem.
   */
  restoreDefaultState(paths?: KeyPath[]): Promise<void> {
    return this.edits.run(() => this.call('restore_default_state', paths ? { paths } : {}));
  }

  /**
   * Keys missing from the state are left as they are. No paths saves every defaultable field. Refused as a whole when
   * the defaults would have a problem. Not undoable.
   */
  saveAsDefaultState(paths?: KeyPath[]): Promise<void> {
    return this.edits.run(() => this.call('save_as_default_state', paths ? { paths } : {}));
  }

  /** Properties by name, plus the position under `position`. Empty when the profile sets nothing on the device. */
  saved(id: string): Record<string, unknown> {
    const profile = this.activeProfile ? this.instrument.state.profile(this.activeProfile) : undefined;
    const kept: Record<string, unknown> = { ...profile?.props[id] };
    if (profile && id in profile.positions) kept.position = profile.positions[id];
    return kept;
  }

  differing(id: string): string[] {
    const device = this.device(id);
    if (!device) return [];
    return Object.entries(this.saved(id))
      .filter(([name, kept]) => device.value(name) !== undefined && !ObjectDiff.same(device.value(name), kept))
      .map(([name]) => name);
  }

  /** Applied as 1 edit. No device changes. */
  saveToProfile(id: string, properties: string[]): Promise<void> {
    return this.edits.run(() => this.call('save_to_profile', { device_id: id, properties }));
  }

  /** Applied as 1 edit. No device changes. */
  removeFromProfile(id: string, properties: string[]): Promise<void> {
    return this.edits.run(() => this.call('remove_from_profile', { device_id: id, properties }));
  }

  /** Autosaved properties are written on every change, so they cannot be removed from the profile. */
  autosaved(id: string, name: string): boolean {
    const list = this.instrument.config?.autosave[id];
    return list === '*' || (list?.includes(name) ?? false);
  }

  /** Not undoable. */
  restoreFromProfile(id: string, properties: string[]): Promise<void> {
    return this.call('restore_from_profile', { device_id: id, properties });
  }

  undo(): Promise<void> {
    return this.edits.run(() => this.call('undo'));
  }

  redo(): Promise<void> {
    return this.edits.run(() => this.call('redo'));
  }

  stop(): Promise<void> {
    return this.call('stop');
  }

  /** A running preview goes dark and keeps running. */
  lasersOff(): Promise<void> {
    return this.call('lasers_off');
  }

  /** A laser blocked further along may stay on. A running preview keeps running. */
  lightsOff(): Promise<void> {
    return this.call('lights_off');
  }

  /** A running preview changes at once. */
  setPowerMode(mode: PowerMode): Promise<void> {
    return this.call('set_power_mode', { mode });
  }

  dispose(): void {
    this.edits.dispose();
  }
}
