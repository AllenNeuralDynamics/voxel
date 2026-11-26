import { Quantity } from '$lib/core/utils/quantity';
import { ObjectDiff } from '@voxel/kit/object-diff';

import { type LightPathPlace, LightPaths } from './light-paths';
import { State } from './state.svelte';
import type { Topics } from './topics.svelte';
import type { DeviceConfig, Filter, InstrumentConfig, InstrumentState, Objective, Part, PassBand } from './types';
import { Wires } from './wires';

/**
 * An instrument as its files describe it, open or not: config, saved state and default state. Devices and commands
 * live in InstrumentSession.
 */
export class Instrument<C extends InstrumentConfig = InstrumentConfig, S extends InstrumentState = InstrumentState> {
  readonly name: string;
  readonly #topics: Topics;

  readonly state: State<S>;
  readonly defaultState: State<S>;

  constructor(name: string, topics: Topics) {
    this.name = name;
    this.#topics = topics;
    this.state = new State<S>(topics.scope('state'));
    this.defaultState = new State<S>(topics.scope('default_state'));
  }

  /**
   * Saved values that differ from the default state. Fields that cannot have a default, such as the plan, do not count.
   */
  get changes(): number {
    const [now, was] = [this.state.value, this.defaultState.value] as Record<string, unknown>[];
    return this.defaultState.fields.reduce((sum, field) => sum + ObjectDiff.count(now[field], was[field]), 0);
  }

  /** The dotted class path of the form that each task's metadata has. */
  get metadataForm(): string | undefined {
    return this.state.get('metadata_cls');
  }

  get config(): C | undefined {
    return this.#topics.get<C>('config');
  }

  /** In rig order: station devices first, then each node's. `node` is null for the station. */
  readonly deviceConfigs: Record<string, { config: DeviceConfig; node: string | null }> = $derived.by(() => {
    const own = Object.entries(this.config?.devices ?? {}).map(([id, config]) => [id, { config, node: null }]);
    const remote = Object.entries(this.config?.nodes ?? {}).flatMap(([node, { devices }]) =>
      Object.entries(devices).map(([id, config]) => [id, { config, node }])
    );
    return Object.fromEntries([...own, ...remote]);
  });
  /** Where the node `name` is on the light paths, with the ways a router sends light; undefined on no path. */
  lightPathOf(name: string): LightPathPlace | undefined {
    const served = this.lightPaths.serves(name);
    if (!served) return undefined;
    const node = this.config?.optics[name];
    const to = node && 'to' in node ? node.to : undefined;
    const ways = to && typeof to === 'object' && !Array.isArray(to) ? to : {};
    return {
      side: served.side,
      serves: served.ends,
      ways: Object.entries(ways).map(([label, way]) => [label, typeof way === 'string' ? [way] : way])
    };
  }

  readonly filters: Record<string, Filter> = $derived.by(() => this.#partsOf<Filter>('filter'));

  readonly objectives: Record<string, Objective> = $derived.by(() => this.#partsOf<Objective>('objective'));

  readonly lightPaths: LightPaths = $derived.by(() => new LightPaths(this.config?.optics ?? {}));

  readonly wires: Wires = $derived.by(() => new Wires(this.config?.wiring ?? {}));

  /**
   * The band every filter between the specimen and `camera` passes under the profile's positions. When the filters
   * share no wavelength, the band of the filter nearest the camera. Undefined when no filter is on the way.
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

  /** Text such as `500 nm` or `0.5 um`, in nm. Null when it is not a wavelength. */
  static #nm(text: string | null): number | null {
    const value = text === null ? undefined : Quantity.parse(text);
    if (!value) return null;
    return value.unit === 'um' ? value.number * 1000 : value.number;
  }

  #partsOf<T extends Part>(kind: T['kind']): Record<string, T> {
    const parts = Object.entries(this.config?.parts ?? {});
    return Object.fromEntries(parts.filter(([, part]) => part.kind === kind)) as Record<string, T>;
  }
}
