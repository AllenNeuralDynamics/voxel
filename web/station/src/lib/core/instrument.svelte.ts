/** An instrument, open or closed: what its files say. */
import { Quantity } from '$lib/core/utils/quantity';
import { ObjectDiff } from '@voxel/kit/object-diff';

import { LightPaths } from './light-paths';
import { State } from './state.svelte';
import type { Topics } from './topics.svelte';
import type { Filter, InstrumentConfig, InstrumentState, Objective, Part, PassBand } from './types';

/**
 * An instrument as its files give it: its config, its saved state and its default state, and what follows from them,
 * such as its light paths. It is the same for an instrument that runs and for one that does not; it has no devices
 * and takes no commands. Those are in the InstrumentSession of the instrument that runs. It reads topics with the
 * names of the feed: `config`, `state.*` and `default_state.*`. It holds what every kind of instrument has; a kind,
 * such as SpimInstrument, extends it, and names the config `C` and the state `S` of its kind.
 */
export class Instrument<C extends InstrumentConfig = InstrumentConfig, S extends InstrumentState = InstrumentState> {
  /** The name of the instrument's folder. */
  readonly name: string;
  readonly #topics: Topics;

  /** The saved state: the profiles, the positions that the instrument sets, the plan. */
  readonly state: State<S>;
  /** The default state, in the same form as `state`. */
  readonly defaultState: State<S>;

  constructor(name: string, topics: Topics) {
    this.name = name;
    this.#topics = topics;
    this.state = new State<S>(topics.scope('state'));
    this.defaultState = new State<S>(topics.scope('default_state'));
  }

  /**
   * How many values of the saved state are not those of the default state, in the fields that the default state
   * has. A field that cannot be a default, such as the plan, does not count.
   */
  get changes(): number {
    const [now, was] = [this.state.value, this.defaultState.value] as Record<string, unknown>[];
    return this.defaultState.fields.reduce((sum, field) => sum + ObjectDiff.count(now[field], was[field]), 0);
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
    const positions = this.state.profile(profileId)?.positions ?? {};
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
}
