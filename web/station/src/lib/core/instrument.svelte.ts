/** The station's open instrument. */
import { Quantity } from '$lib/core/utils/quantity';
import { TaskChain } from '$lib/core/utils/task-chain.svelte';

import type { Client } from './client.svelte';
import { Device, Laser, Modulator, Shutter } from './device.svelte';
import { LightPaths } from './light-paths';
import type { Topics } from './topics.svelte';
import type {
  ActivityInfo,
  Alert,
  Filter,
  HttpInstrumentInterface,
  InstrumentConfig,
  Objective,
  Part,
  PassBand,
  PowerMode,
  Profile
} from './types';

/**
 * The open instrument of 1 session: its state and devices, read from the feed topics `instrument.*`, and the steps that
 * change it, sent to `<station>/instrument`. An edit of the instrument's state goes through `edits`, in order; a step
 * that drives the hardware, such as turning the lasers off, is sent at once. It holds what every kind of instrument
 * has; a kind with more, such as SpimInstrument, extends it, and names the config `C` and the profile `P` of its kind.
 */
/** 1 laser's light on its way to the sample: the laser, the modulators and shutters that only its light passes, and
 * whether the light reaches the sample now. */
export interface Beam {
  source: Laser;
  own: (Modulator | Shutter)[];
  reaches: boolean;
  blockedBy: Modulator | Shutter | undefined;
}

export class Instrument<C extends InstrumentConfig = InstrumentConfig, P extends Profile = Profile> {
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

  /** The part `name` of the instrument's view, as the feed sends it. For a kind's own parts. */
  protected view<T>(name: string): T | undefined {
    return this.#topics.get<T>(name);
  }

  get config(): C | undefined {
    return this.#topics.get<C>('config');
  }

  /** The filters among the config's parts, by name. */
  readonly filters: Record<string, Filter> = $derived.by(() => this.#partsOf<Filter>('filter'));

  /** The objectives among the config's parts, by name. */
  readonly objectives: Record<string, Objective> = $derived.by(() => this.#partsOf<Objective>('objective'));

  /** The light paths of the config's optical graph, worked out once for each config. */
  readonly lightPaths: LightPaths = $derived.by(() => new LightPaths(this.config?.optics ?? {}));

  /**
   * The wavelengths that reach `camera` with the positions of the profile `profileId`: what every filter on the way
   * from the specimen lets through. A filter on the way is a node that is a filter, or the filter that the profile
   * puts a node at. When the filters share no wavelength, it is the band of the filter nearest the camera. Undefined
   * when no filter is on the way.
   */
  passBand(profileId: string, camera: string): PassBand | undefined {
    const positions = this.profile(profileId)?.positions ?? {};
    const ways = this.lightPaths.to(camera);
    const way =
      ways.find((path) => Object.entries(path.positions).every(([router, label]) => positions[router] === label)) ??
      ways[0];
    const bands = (way?.nodes ?? []).flatMap((node): PassBand[] => {
      const at = positions[node];
      const filter = this.filters[node] ?? (typeof at === 'string' ? this.filters[at] : undefined);
      return filter ? [[Instrument.#nm(filter.band[0]), Instrument.#nm(filter.band[1])]] : [];
    });
    if (bands.length === 0) return undefined;
    const lows = bands.flatMap(([low]) => low ?? []);
    const highs = bands.flatMap(([, high]) => high ?? []);
    const low = lows.length > 0 ? Math.max(...lows) : null;
    const high = highs.length > 0 ? Math.min(...highs) : null;
    return low !== null && high !== null && low > high ? bands[bands.length - 1] : [low, high];
  }

  /** A wavelength as text, such as `500 nm` or `0.5 um`, in nm. Null for null and for text that is no wavelength. */
  static #nm(text: string | null): number | null {
    const value = text === null ? undefined : Quantity.parse(text);
    if (!value) return null;
    return value.unit === 'um' ? value.number * 1000 : value.number;
  }

  /** The config's parts of 1 kind, by name. */
  #partsOf<T extends Part>(kind: T['kind']): Record<string, T> {
    const parts = Object.entries(this.config?.parts ?? {});
    return Object.fromEntries(parts.filter(([, part]) => part.kind === kind)) as Record<string, T>;
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

  /** The ids of the saved profiles. */
  get profileIds(): string[] {
    return this.#topics.names('state.profiles');
  }

  /** The profile `id`, or undefined. */
  profile(id: string): P | undefined {
    return this.#topics.get<P>(`state.profiles.${id}`);
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
        const ways = this.lightPaths.from(source.id).map((path) => path.nodes.flatMap((node) => gates.get(node) ?? []));
        const blockers = ways.map((way) => way.find(stops));
        const open = ways.length === 0 || blockers.some((blocker) => blocker === undefined);
        const own = [...new Set(ways.flat())].filter((gate) => this.lightPaths.serves(gate.id)?.ends.length === 1);
        return { source, own, reaches: source.isOn && open, blockedBy: source.isOn && !open ? blockers[0] : undefined };
      });
  });

  /** The modulators and shutters that the light of several lasers passes, in the order of the light's way. */
  readonly sharedGates: (Modulator | Shutter)[] = $derived.by(() =>
    this.devices.filter(
      (device): device is Modulator | Shutter =>
        (device instanceof Modulator || device instanceof Shutter) &&
        (this.lightPaths.serves(device.id)?.ends.length ?? 0) > 1
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
