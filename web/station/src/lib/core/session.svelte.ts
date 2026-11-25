/** The session of the instrument that runs: its devices, and the steps that change it. */
import { TaskChain } from '$lib/core/utils/task-chain.svelte';

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

/** 1 laser's light on its way to the sample: the laser, the modulators and shutters that only its light passes, and
 * whether the light reaches the sample now. */
export interface Beam {
  source: Laser;
  own: (Modulator | Shutter)[];
  reaches: boolean;
  blockedBy: Modulator | Shutter | undefined;
}

/**
 * The session of the instrument that runs: the instrument itself, its devices, read from the feed topics
 * `instrument.*`, and the steps that change it, sent to `<station>/instrument`. An edit of the instrument's state goes
 * through `edits`, in order; a step that drives the hardware, such as turning the lasers off, is sent at once. Data
 * comes from `instrument`, and actions from the session. It holds what every kind of instrument has; a kind with
 * more, such as SpimSession, extends it, and names the class `I` of its instrument.
 */
export class InstrumentSession<I extends Instrument = Instrument> {
  /** The id of the session. A new one for each time an instrument opens. */
  readonly id: string;
  /** The instrument that runs. */
  readonly instrument: I;
  readonly edits = new TaskChain();
  readonly #client: Client;
  readonly #topics: Topics;
  readonly #base: string;
  readonly #devices = new Map<string, Device>();

  /** What a client can ask this instrument and how it reaches each operation, or undefined until it loads. */
  interface = $state.raw<HttpInstrumentInterface | undefined>(undefined);

  constructor(client: Client, topics: Topics, base: string, id: string, instrument: I) {
    this.id = id;
    this.instrument = instrument;
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

  /** The part `name` of the instrument's view, as the feed sends it. For a kind's own parts. */
  protected view<T>(name: string): T | undefined {
    return this.#topics.get<T>(name);
  }

  /** The id of the profile in use, or undefined. */
  get activeProfile(): string | undefined {
    return this.#topics.get<string>('active_profile');
  }

  /** The name of the operation that runs now, or null. */
  get operation(): string | null {
    return this.#topics.get<string>('operation') ?? null;
  }

  /** Which powers of the active profile are in use: the full ones or the dim ones. */
  get powerMode(): PowerMode | undefined {
    return this.#topics.get<PowerMode>('power_mode');
  }

  /** What is wrong now. */
  get alerts(): Alert[] {
    return this.#topics.get<Alert[]>('alerts') ?? [];
  }

  /** What the instrument runs now, such as a preview or an acquisition. */
  get activities(): ActivityInfo[] {
    return this.#topics.get<ActivityInfo[]>('activities') ?? [];
  }

  /** The running activity of `kind`, or undefined. */
  activity<T extends ActivityInfo = ActivityInfo>(kind: T['kind']): T | undefined {
    return this.activities.find((activity) => activity.kind === kind) as T | undefined;
  }

  /** The undo history of the saved state: what the next undo and the next redo are. Not the past runs. */
  get history(): HistoryState {
    return this.#topics.get<HistoryState>('history') ?? { undo_label: null, redo_label: null };
  }

  /**
   * The devices that the feed sends, each as the class of its kind. A device is made once, when the feed has its
   * interface, and kept while its id stays.
   */
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
   * Each laser's light on its way to the sample, in wavelength order. `own` holds the modulators and shutters that
   * only this laser's light passes, in the order of the light's way. The light reaches the sample when the laser is on
   * and, on 1 of its ways, every modulator is on and every shutter is open; else `blockedBy` is the first device that
   * stops it.
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

  /** The modulators and shutters that the light of several lasers passes, in the order of the light's way. */
  readonly sharedGates: (Modulator | Shutter)[] = $derived.by(() =>
    this.devices.filter(
      (device): device is Modulator | Shutter =>
        (device instanceof Modulator || device instanceof Shutter) &&
        (this.instrument.lightPaths.serves(device.id)?.ends.length ?? 0) > 1
    )
  );

  /** The devices of 1 class, such as every Dimmable. */
  devicesOf<T extends Device>(type: new (...args: never[]) => T): T[] {
    return this.devices.filter((device): device is T => device instanceof type);
  }

  /** The device `id`, or undefined. With `type`, undefined too when the device is not of that class. */
  device(id: string): Device | undefined;
  device<T extends Device>(id: string, type: new (...args: never[]) => T): T | undefined;
  device<T extends Device>(id: string, type?: new (...args: never[]) => T): Device | T | undefined {
    const device = this.devices.find((found) => found.id === id);
    return !type || device instanceof type ? device : undefined;
  }

  selectProfile(id: string): Promise<void> {
    return this.edits.run(() => this.call('select_profile', { profile_id: id }));
  }

  /** Changes `fields` of the profile `id`, as 1 edit. */
  updateProfile(id: string, fields: ProfileFields): Promise<void> {
    return this.edits.run(() => this.call('update_profile', { profile_id: id, ...fields }));
  }

  /**
   * Loads `timeline` into the signal generator `generator`, and saves it into the active profile. The instrument
   * refuses a timeline that does not fit, before the generator changes. An undo does not take it back.
   */
  setGeneratorTimeline(generator: string, timeline: Timeline): Promise<void> {
    return this.edits.run(() => this.call('set_generator_timeline', { generator, timeline }));
  }

  /**
   * Sets 1 number of the signal on `wire` in the active profile's timeline of `generator`, as a tuning knob does,
   * and gives the value that the instrument took. `value` is in the fixed unit of `field`. An undo does not take it
   * back.
   */
  setTuningKnob(generator: string, wire: string, field: TuningField, value: number): Promise<number> {
    return this.edits.run(() => this.call<number>('set_tuning_knob', { generator, wire, field, value }));
  }

  /**
   * Sets the state at each path back to the default state, as 1 edit. A key that the defaults do not have leaves the
   * state. With no paths, every field that can be a default goes back. The instrument refuses all of it when the
   * state would have a problem.
   */
  restoreDefaultState(paths?: KeyPath[]): Promise<void> {
    return this.edits.run(() => this.call('restore_default_state', paths ? { paths } : {}));
  }

  /**
   * Saves the state at each path as the default state. A key that the state does not have leaves the defaults. With
   * no paths, every field that can be a default is saved. The instrument refuses all of it when the defaults would
   * have a problem. An undo does not take it back.
   */
  saveAsDefaultState(paths?: KeyPath[]): Promise<void> {
    return this.edits.run(() => this.call('save_as_default_state', paths ? { paths } : {}));
  }

  undo(): Promise<void> {
    return this.edits.run(() => this.call('undo'));
  }

  redo(): Promise<void> {
    return this.edits.run(() => this.call('redo'));
  }

  /** Stops what the instrument is doing now, such as the preview or an acquisition. */
  stop(): Promise<void> {
    return this.call('stop');
  }

  /** Turns off every laser and modulator, and closes every shutter. A running preview goes dark and keeps running. */
  lasersOff(): Promise<void> {
    return this.call('lasers_off');
  }

  /** Makes every light dark; a laser whose light is blocked further along may stay on. A running preview keeps running. */
  lightsOff(): Promise<void> {
    return this.call('lights_off');
  }

  /** Uses the full or the dim powers of the active profile. A running preview changes at once. */
  setPowerMode(mode: PowerMode): Promise<void> {
    return this.call('set_power_mode', { mode });
  }

  /** Refuses every edit from now on, once the session ends. */
  dispose(): void {
    this.edits.dispose();
  }
}
