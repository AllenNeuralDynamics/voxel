import { Prefs } from '$lib/core/prefs';
import { isValidHex } from '@voxel/kit/colors';

/** Colors run darkest to brightest. `changed` marks an edited default. */
export interface Colormap {
  id: string;
  name: string;
  stops: string[];
  own: boolean;
  changed: boolean;
}

/** `hidden` keeps the group out of the choice lists. */
export interface ColormapGroup {
  id: string;
  label: string;
  ids: string[];
  own: boolean;
  hidden: boolean;
  changed: boolean;
}

/** Only the fields that differ from the defaults. */
interface DefaultChanges {
  colormaps: Record<string, { name?: string; stops?: string[] }>;
  groups: Record<string, { label?: string; ids?: string[]; hidden?: boolean }>;
}

/**
 * Colormaps and their groups. A colormap can be in any number of groups; a default colormap's id is its first name.
 * Default edits and own items are saved apart, so resetting defaults keeps own items. A channel choice is a colormap id,
 * a hex color (black to that color) or `AUTO`.
 */
export class Colormaps {
  static readonly AUTO = 'auto';
  static readonly #BLACK = '#000000';
  static readonly #WHITE = '#ffffff';

  static readonly DEFAULTS: Readonly<Record<string, string[]>> = {
    red: ['#ff0000'],
    green: ['#00ff00'],
    blue: ['#0000ff'],
    cyan: ['#00ffff'],
    magenta: ['#ff00ff'],
    yellow: ['#ffff00'],
    orange: ['#ffa500'],
    white: ['#ffffff'],
    farred: ['#aa0066'],
    gfp: ['#00ff00'],
    egfp: ['#00ff00'],
    yfp: ['#ffff00'],
    eyfp: ['#ffff00'],
    citrine: ['#ffff00'],
    venus: ['#ffff00'],
    rfp: ['#ff6600'],
    dsred: ['#ff0000'],
    mcherry: ['#ff0066'],
    tdtomato: ['#ff4500'],
    mkate2: ['#ff0033'],
    cfp: ['#00ffff'],
    ecfp: ['#00ffff'],
    cerulean: ['#00ccff'],
    mplum: ['#cc00ff'],
    katushka: ['#ff0066'],
    dapi: ['#0066ff'],
    hoechst: ['#0066ff'],
    draq5: ['#aa0066'],
    pi: ['#ff0000'],
    alexa488: ['#00ff99'],
    alexa555: ['#ffaa00'],
    alexa594: ['#ff6600'],
    alexa647: ['#ff0066'],
    cy3: ['#ffaa00'],
    cy5: ['#ff0066'],
    cy7: ['#990033'],
    atto488: ['#00ff99'],
    atto565: ['#ff9900'],
    atto647n: ['#ff0066'],
    fitc: ['#00ff00'],
    tritc: ['#ff6600'],
    rhodamine: ['#ff0066'],
    tamra: ['#ffaa00'],
    gcamp: ['#00ff00'],
    gcamp6: ['#00ff00'],
    gcamp7: ['#00ff00'],
    rhod2: ['#ff0066'],
    fluo4: ['#00ff00'],
    fluo8: ['#00ff00'],
    cal520: ['#00ff99'],
    asap: ['#00ff99'],
    asap3: ['#00ff99'],
    archer: ['#00ff00'],
    phrodo: ['#ff0066'],
    dil: ['#ff6600'],
    dio: ['#00ff00'],
    mitotracker: ['#ff0066'],
    tmrm: ['#ff6600'],
    inferno: ['#000003', '#270b52', '#65156e', '#9e2963', '#d44841', '#f57c15', '#fac128', '#fcfea4'],
    viridis: ['#440154', '#46317e', '#365b8c', '#277e8e', '#1fa187', '#49c16d', '#9fd938', '#fde724'],
    magma: ['#000003', '#221150', '#5e177f', '#972c7f', '#d3426d', '#f8755c', '#febb80', '#fbfcbf'],
    plasma: ['#0c0786', '#5201a3', '#8b09a4', '#b83289', '#db5b67', '#f38748', '#fdbc2a', '#eff821'],
    cividis: ['#00224d', '#213b6e', '#4c546c', '#6c6d72', '#8d8978', '#b1a570', '#d8c45b', '#fde737'],
    turbo: ['#30123b', '#4675ed', '#1bcfd4', '#61fc6c', '#d1e834', '#fe9b2d', '#d93806', '#7a0402'],
    hot: ['#0a0000', '#690000', '#ca0000', '#ff2900', '#ff8a00', '#ffe900', '#ffff71', '#ffffff'],
    cool: ['#00ffff', '#24dbff', '#49b6ff', '#6d92ff', '#926dff', '#b649ff', '#db24ff', '#ff00ff'],
    coolwarm: ['#3a4cc0', '#6788ed', '#99bafe', '#c8d7ef', '#edd0c1', '#f6a789', '#e16852', '#b30326'],
    gray: ['#000000', '#242424', '#494949', '#6d6d6d', '#929292', '#b6b6b6', '#dbdbdb', '#ffffff'],
    grayscale: ['#000000', '#242424', '#494949', '#6d6d6d', '#929292', '#b6b6b6', '#dbdbdb', '#ffffff'],
    bone: ['#000000', '#1f1f2b', '#3f3f58', '#5f647f', '#7f919f', '#9fbcbf', '#cddfdf', '#ffffff'],
    copper: ['#000000', '#2c1c11', '#5a3924', '#865536', '#b47248', '#e08e5a', '#ffab6c', '#ffc77e'],
    jet: ['#00007f', '#0010ff', '#00a4ff', '#3fffb7', '#b7ff3f', '#ffb900', '#ff3000', '#7f0000']
  };

  static readonly DEFAULT_GROUPS: readonly Readonly<{ id: string; label: string; ids: string[]; hidden?: boolean }>[] =
    [
      {
        id: 'fluorescent_proteins',
        label: 'Fluorescent Proteins',
        ids: [
          'gfp',
          'egfp',
          'yfp',
          'eyfp',
          'citrine',
          'venus',
          'rfp',
          'dsred',
          'mcherry',
          'tdtomato',
          'mkate2',
          'cfp',
          'ecfp',
          'cerulean',
          'mplum',
          'katushka'
        ]
      },
      { id: 'nuclear_stains', label: 'Nuclear Stains', ids: ['dapi', 'hoechst', 'draq5', 'pi'] },
      { id: 'alexa_dyes', label: 'Alexa Dyes', ids: ['alexa488', 'alexa555', 'alexa594', 'alexa647'], hidden: true },
      { id: 'cy_dyes', label: 'Cy Dyes', ids: ['cy3', 'cy5', 'cy7'], hidden: true },
      { id: 'atto_dyes', label: 'ATTO Dyes', ids: ['atto488', 'atto565', 'atto647n'], hidden: true },
      {
        id: 'classic_fluorophores',
        label: 'Classic Fluorophores',
        ids: ['fitc', 'tritc', 'rhodamine', 'tamra'],
        hidden: true
      },
      {
        id: 'functional_indicators',
        label: 'Functional Indicators',
        ids: ['gcamp', 'gcamp6', 'gcamp7', 'rhod2', 'fluo4', 'fluo8', 'cal520', 'asap', 'asap3', 'archer', 'phrodo'],
        hidden: true
      },
      { id: 'organelle_stains', label: 'Organelle Stains', ids: ['dil', 'dio', 'mitotracker', 'tmrm'], hidden: true },
      {
        id: 'basic',
        label: 'Basic Colors',
        ids: ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow', 'orange', 'white', 'farred']
      },
      {
        id: 'gradients',
        label: 'Gradients',
        ids: [
          'inferno',
          'viridis',
          'magma',
          'plasma',
          'cividis',
          'turbo',
          'hot',
          'cool',
          'coolwarm',
          'gray',
          'grayscale',
          'bone',
          'copper',
          'jet'
        ]
      }
    ];

  readonly #changes = Prefs.colormaps.pref<DefaultChanges>('defaults', { colormaps: {}, groups: {} });
  readonly #order = Prefs.colormaps.pref<string[]>('order', []);
  readonly #own = Prefs.myColormaps.pref<Record<string, { name: string; stops: string[] }>>('colormaps', {});
  readonly #ownGroups = Prefs.myColormaps.pref<Record<string, { label: string; ids: string[]; hidden?: boolean }>>(
    'groups',
    {}
  );

  readonly all: Colormap[] = $derived.by(() =>
    [...Object.keys(Colormaps.DEFAULTS), ...Object.keys(this.#own.get())].flatMap((id) => this.get(id) ?? [])
  );

  /** Without a saved order, own groups come first, newest on top; unordered groups go last. */
  readonly groups: ColormapGroup[] = $derived.by(() => {
    const order = this.#order.get();
    const place = (id: string): number => (order.includes(id) ? order.indexOf(id) : order.length);
    return this.#natural().toSorted((a, b) => place(a.id) - place(b.id));
  });

  readonly shownGroups: ColormapGroup[] = $derived.by(() =>
    this.groups.filter((group) => !group.hidden && group.ids.length > 0)
  );

  readonly ungrouped: string[] = $derived.by(() => {
    const grouped = new Set(this.groups.flatMap((group) => group.ids));
    return Object.keys(this.#own.get()).filter((id) => !grouped.has(id));
  });

  get(id: string): Colormap | undefined {
    const own = this.#own.get()[id];
    if (own) return { id, name: own.name, stops: own.stops, own: true, changed: false };
    if (!Object.hasOwn(Colormaps.DEFAULTS, id)) return undefined;
    const change = this.#changes.get().colormaps[id];
    return {
      id,
      name: change?.name ?? id,
      stops: change?.stops ?? Colormaps.DEFAULTS[id],
      own: false,
      changed: change !== undefined
    };
  }

  has(choice: string): boolean {
    return this.get(choice) !== undefined || isValidHex(choice);
  }

  name(choice: string): string {
    return this.get(choice)?.name ?? choice;
  }

  /** Black to white for an unknown choice. */
  stops(choice: string): string[] {
    if (isValidHex(choice)) return [Colormaps.#BLACK, choice];
    const stops = this.get(choice)?.stops;
    if (!stops || stops.length === 0) return [Colormaps.#BLACK, Colormaps.#WHITE];
    return stops.length === 1 ? [Colormaps.#BLACK, stops[0]] : stops;
  }

  color(choice: string): string {
    const stops = this.stops(choice);
    return stops[stops.length - 1];
  }

  gradient(choice: string): string {
    return `linear-gradient(to right, ${this.stops(choice).join(', ')})`;
  }

  /** Raises an error unless `stops` is 1 or more hex colors. */
  create(name: string, stops: string[]): string {
    Colormaps.#checkStops(stops);
    const id = `own-${crypto.randomUUID()}`;
    this.#own.set({ ...this.#own.get(), [id]: { name, stops: [...stops] } });
    return id;
  }

  /** An empty name changes nothing. */
  setName(id: string, name: string): void {
    if (name === '') return;
    const own = this.#own.get();
    if (own[id]) this.#own.set({ ...own, [id]: { ...own[id], name } });
    else this.#changeColormap(id, { name: name === id ? undefined : name });
  }

  /** Raises an error unless `stops` is 1 or more hex colors. */
  setStops(id: string, stops: string[]): void {
    Colormaps.#checkStops(stops);
    const own = this.#own.get();
    if (own[id]) this.#own.set({ ...own, [id]: { ...own[id], stops: [...stops] } });
    else this.#changeColormap(id, { stops: Colormaps.#same(stops, Colormaps.DEFAULTS[id]) ? undefined : [...stops] });
  }

  reset(id: string): void {
    this.#changeColormap(id, { name: undefined, stops: undefined });
  }

  /** Also removes it from every group. */
  remove(id: string): void {
    const own = this.#own.get();
    if (!own[id]) return;
    this.#own.set(Object.fromEntries(Object.entries(own).filter(([key]) => key !== id)));
    for (const group of this.groups) {
      if (group.ids.includes(id)) this.removeFrom(group.id, id);
    }
  }

  addGroup(label: string): string {
    const id = `own-${crypto.randomUUID()}`;
    this.#ownGroups.set({ ...this.#ownGroups.get(), [id]: { label, ids: [] } });
    const order = this.#order.get();
    if (order.length > 0) this.#order.set([id, ...order]);
    return id;
  }

  /** An empty label changes nothing. */
  setLabel(group: string, label: string): void {
    if (label === '') return;
    const own = this.#ownGroups.get();
    if (own[group]) this.#ownGroups.set({ ...own, [group]: { ...own[group], label } });
    else this.#changeGroup(group, { label: label === Colormaps.#defaultGroup(group)?.label ? undefined : label });
  }

  /** Its colormaps stay. */
  removeGroup(group: string): void {
    const own = this.#ownGroups.get();
    if (!own[group]) return;
    this.#ownGroups.set(Object.fromEntries(Object.entries(own).filter(([key]) => key !== group)));
    this.#order.set(this.#order.get().filter((id) => id !== group));
  }

  resetGroup(group: string): void {
    this.#changeGroup(group, { label: undefined, ids: undefined, hidden: undefined });
  }

  orderGroups(ids: string[]): void {
    this.#order.set(
      Colormaps.#same(
        ids,
        this.#natural().map((group) => group.id)
      )
        ? []
        : ids
    );
  }

  addTo(group: string, id: string): void {
    const ids = this.groups.find((each) => each.id === group)?.ids;
    if (ids && !ids.includes(id)) this.#setIds(group, [...ids, id]);
  }

  removeFrom(group: string, id: string): void {
    const ids = this.groups.find((each) => each.id === group)?.ids;
    if (ids?.includes(id)) {
      this.#setIds(
        group,
        ids.filter((each) => each !== id)
      );
    }
  }

  setHidden(group: string, hidden: boolean): void {
    const own = this.#ownGroups.get();
    if (own[group]) {
      const { label, ids } = own[group];
      this.#ownGroups.set({ ...own, [group]: hidden ? { label, ids, hidden } : { label, ids } });
    } else {
      const fromCode = Colormaps.#defaultGroup(group)?.hidden ?? false;
      this.#changeGroup(group, { hidden: hidden === fromCode ? undefined : hidden });
    }
  }

  #natural(): ColormapGroup[] {
    const exists = (id: string): boolean => this.get(id) !== undefined;
    const changes = this.#changes.get().groups;
    const own = Object.entries(this.#ownGroups.get()).map(([id, group]): ColormapGroup => ({
      id,
      label: group.label,
      ids: group.ids.filter(exists),
      own: true,
      hidden: group.hidden ?? false,
      changed: false
    }));
    const fixed = Colormaps.DEFAULT_GROUPS.map((group): ColormapGroup => {
      const change = changes[group.id];
      return {
        id: group.id,
        label: change?.label ?? group.label,
        ids: (change?.ids ?? group.ids).filter(exists),
        own: false,
        hidden: change?.hidden ?? group.hidden ?? false,
        changed: change !== undefined
      };
    });
    return [...own.toReversed(), ...fixed];
  }

  #setIds(group: string, ids: string[]): void {
    const own = this.#ownGroups.get();
    if (own[group]) this.#ownGroups.set({ ...own, [group]: { ...own[group], ids } });
    else this.#changeGroup(group, { ids: Colormaps.#same(ids, Colormaps.#defaultGroup(group)?.ids) ? undefined : ids });
  }

  /** Undefined fields are dropped, and an empty change is removed. */
  #changeColormap(id: string, fields: DefaultChanges['colormaps'][string]): void {
    if (!Object.hasOwn(Colormaps.DEFAULTS, id)) return;
    const { colormaps, groups } = this.#changes.get();
    this.#changes.set({ colormaps: Colormaps.#merged(colormaps, id, fields), groups });
  }

  #changeGroup(id: string, fields: DefaultChanges['groups'][string]): void {
    if (!Colormaps.#defaultGroup(id)) return;
    const { colormaps, groups } = this.#changes.get();
    this.#changes.set({ colormaps, groups: Colormaps.#merged(groups, id, fields) });
  }

  static #merged<T extends object>(table: Record<string, T>, id: string, fields: T): Record<string, T> {
    const entry = Object.fromEntries(
      Object.entries({ ...table[id], ...fields }).filter(([, value]) => value !== undefined)
    ) as T;
    const rest = Object.fromEntries(Object.entries(table).filter(([key]) => key !== id));
    return Object.keys(entry).length > 0 ? { ...rest, [id]: entry } : rest;
  }

  static #defaultGroup(id: string): (typeof Colormaps.DEFAULT_GROUPS)[number] | undefined {
    return Colormaps.DEFAULT_GROUPS.find((group) => group.id === id);
  }

  static #same(a: readonly string[], b: readonly string[] | undefined): boolean {
    return b !== undefined && a.length === b.length && a.every((each, index) => each === b[index]);
  }

  static #checkStops(stops: string[]): void {
    if (stops.length === 0 || !stops.every((stop) => isValidHex(stop))) {
      throw new Error('A colormap needs 1 or more hex colors');
    }
  }
}
