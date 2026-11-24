import { SvelteMap } from 'svelte/reactivity';

/** The saved values of a group, by the name of each value. */
export type SavedPrefs = Record<string, unknown>;

export interface PrefGroupOptions {
  /** The version of the form of the group's values. It is 1 when left out. */
  version?: number;
  /** Changes values saved in the form of the version `from` into the form of `version`. */
  migrate?: (saved: SavedPrefs, from: number) => SavedPrefs;
}

/**
 * 1 saved value of a group, with its default. A value that is equal to the default is not saved, so `changed` is true
 * only for a value that differs from it. A saved value that `check` refuses counts as not saved. Reads take part in
 * Svelte reactivity. `get` and `set` work as loose functions: `bind:x={pref.get, pref.set}`.
 */
export class Pref<T> {
  readonly #initial: T;
  readonly #text: () => string | undefined;
  readonly #write: (value: T | undefined) => void;
  readonly #check: ((value: unknown) => boolean) | undefined;
  // The value of the text that was read last, so a value is the same object until its text changes.
  #last: { text: string; value: T | undefined } | undefined;

  /** Made by `PrefGroup.pref`. */
  constructor(
    initial: T,
    text: () => string | undefined,
    write: (value: T | undefined) => void,
    check?: (value: unknown) => boolean
  ) {
    this.#initial = initial;
    this.#text = text;
    this.#write = write;
    this.#check = check;
  }

  readonly get = (): T => this.#saved() ?? this.#initial;

  readonly set = (value: T): void => {
    this.#write(JSON.stringify(value) === JSON.stringify(this.#initial) ? undefined : value);
  };

  /** Whether a value that differs from the default is saved. */
  get changed(): boolean {
    return this.#saved() !== undefined;
  }

  /** Drops the saved value, so the value is the default again. */
  reset(): void {
    this.#write(undefined);
  }

  #saved(): T | undefined {
    const text = this.#text();
    if (text === undefined) return undefined;
    if (this.#last?.text !== text) {
      let value: T | undefined;
      try {
        const parsed: unknown = JSON.parse(text);
        value = parsed !== undefined && (this.#check?.(parsed) ?? true) ? (parsed as T) : undefined;
      } catch {
        value = undefined;
      }
      this.#last = { text, value };
    }
    return this.#last.value;
  }
}

/**
 * A group of values that this browser saves, under the keys `voxel:<id>:<name>`. Only a value that differs from its
 * default is saved, so the group is `changed` exactly when it has a saved value, and `reset` puts every value back to
 * its default. A change in another window of this browser shows here at once. The owner of a group makes it 1 time and
 * other code imports it; a second group with the same id, as a module that loads again makes, shares the values of the
 * first.
 *
 * The group has a version. When the saved values are of another version, `migrate` changes them to the form of this
 * one; with no `migrate` they are dropped.
 */
export class PrefGroup {
  static readonly #VERSIONS = 'voxel:versions';
  // The saved values of each group as JSON text, by name. It is the copy that the page reads.
  static readonly #tables = new Map<string, SvelteMap<string, string>>();

  readonly id: string;
  readonly #prefix: string;
  readonly #version: number;
  readonly #entries: SvelteMap<string, string>;

  constructor(id: string, options: PrefGroupOptions = {}) {
    this.id = id;
    this.#prefix = `voxel:${id}:`;
    this.#version = options.version ?? 1;
    const existing = PrefGroup.#tables.get(id);
    this.#entries = existing ?? new SvelteMap<string, string>();
    if (existing || typeof window === 'undefined') return;
    PrefGroup.#tables.set(id, this.#entries);

    const prefix = this.#prefix;
    const entries = this.#entries;
    for (const [key, text] of PrefGroup.#stored()) {
      if (key.startsWith(prefix)) entries.set(key.slice(prefix.length), text);
    }
    const from = PrefGroup.#versions()[id] ?? 1;
    if (entries.size > 0 && from !== this.#version) {
      this.saved = options.migrate ? options.migrate(this.saved, from) : {};
    }
    this.#mark();

    window.addEventListener('storage', (event) => {
      if (event.storageArea !== localStorage) return;
      if (event.key === null) entries.clear();
      else if (!event.key.startsWith(prefix)) return;
      else if (event.newValue === null) entries.delete(event.key.slice(prefix.length));
      else entries.set(event.key.slice(prefix.length), event.newValue);
    });
  }

  /** The value `name` of this group, with its default `initial`. A saved value that `check` refuses is not used. */
  pref<T>(name: string, initial: T, check?: (value: unknown) => boolean): Pref<T> {
    return new Pref<T>(
      initial,
      () => this.#entries.get(name),
      (value) => this.#store(name, value === undefined ? undefined : JSON.stringify(value)),
      check
    );
  }

  /** Every saved value, by name. To set it replaces them all: `{}` is a reset, and a copy read before puts it back. */
  get saved(): SavedPrefs {
    const values: SavedPrefs = {};
    for (const [name, text] of this.#entries) {
      try {
        values[name] = JSON.parse(text);
      } catch {
        // Text that is not JSON is no value.
      }
    }
    return values;
  }

  set saved(values: SavedPrefs) {
    const gone = Array.from(this.#entries.keys()).filter((name) => values[name] === undefined);
    for (const name of gone) this.#store(name, undefined);
    for (const [name, value] of Object.entries(values)) {
      if (value !== undefined) this.#store(name, JSON.stringify(value));
    }
  }

  /** Whether a value of the group differs from its default. */
  get changed(): boolean {
    return this.#entries.size > 0;
  }

  /** Puts every value of the group back to its default. */
  reset(): void {
    this.saved = {};
  }

  #store(name: string, text: string | undefined): void {
    if (text === this.#entries.get(name)) return;
    if (text === undefined) this.#entries.delete(name);
    else this.#entries.set(name, text);
    try {
      if (text === undefined) localStorage.removeItem(this.#prefix + name);
      else localStorage.setItem(this.#prefix + name, text);
    } catch {
      // The browser refused: the value then holds only while this window is open.
    }
    this.#mark();
  }

  /** Keeps the version of the saved values beside them: this group's version while it has values, and none without. */
  #mark(): void {
    const versions = PrefGroup.#versions();
    const wanted = this.#entries.size > 0 ? this.#version : undefined;
    if (versions[this.id] === wanted) return;
    if (wanted === undefined) delete versions[this.id];
    else versions[this.id] = wanted;
    try {
      if (Object.keys(versions).length === 0) localStorage.removeItem(PrefGroup.#VERSIONS);
      else localStorage.setItem(PrefGroup.#VERSIONS, JSON.stringify(versions));
    } catch {
      // As in `#store`.
    }
  }

  static #versions(): Record<string, number> {
    try {
      const versions: unknown = JSON.parse(localStorage.getItem(PrefGroup.#VERSIONS) ?? '{}');
      return versions !== null && typeof versions === 'object' ? (versions as Record<string, number>) : {};
    } catch {
      return {};
    }
  }

  static #stored(): [key: string, text: string][] {
    try {
      return Object.entries(localStorage);
    } catch {
      return [];
    }
  }
}
