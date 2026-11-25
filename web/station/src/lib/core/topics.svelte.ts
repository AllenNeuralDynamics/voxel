/** The topics of the state feed, as a reactive store. */
import { SvelteMap } from 'svelte/reactivity';

import type { StateMessage } from './client.svelte';

/**
 * The last value of each topic of the state feed. Reading 1 topic tracks only that topic. A scope is the same store
 * seen from a prefix, so `scope('stations.a').get('status')` reads `stations.a.status`. Only the Client writes, with
 * `apply`.
 */
export class Topics {
  readonly #cells: SvelteMap<string, unknown>;
  readonly #prefix: string;

  constructor(cells = new SvelteMap<string, unknown>(), prefix = '') {
    this.#cells = cells;
    this.#prefix = prefix;
  }

  /** The value of the topic `name`, or undefined. */
  get<T>(name: string): T | undefined {
    return this.#cells.get(this.#prefix + name) as T | undefined;
  }

  /** Whether the topic `name` has a value. */
  has(name: string): boolean {
    return this.#cells.has(this.#prefix + name);
  }

  /**
   * The next name part of each topic under `prefix`, in order of arrival: `names('devices')` gives the device ids.
   * With no prefix, the first name part of each topic. It changes only when a topic is added or removed.
   */
  names(prefix = ''): string[] {
    const start = prefix ? `${this.#prefix}${prefix}.` : this.#prefix;
    const found = new Set<string>();
    for (const key of this.#cells.keys()) {
      if (key.startsWith(start)) found.add(key.slice(start.length).split('.', 1)[0]);
    }
    return [...found];
  }

  /** The same store, seen from `prefix`. */
  scope(prefix: string): Topics {
    return new Topics(this.#cells, `${this.#prefix}${prefix}.`);
  }

  /** Apply 1 feed message. A full message also removes each topic that it does not name; `null` removes 1 topic. */
  apply(message: StateMessage): void {
    if (message.full) {
      for (const key of this.#cells.keys()) {
        if (!Object.hasOwn(message.topics, key)) this.#cells.delete(key);
      }
    }
    for (const [key, value] of Object.entries(message.topics)) {
      if (value === null) this.#cells.delete(key);
      else this.#cells.set(key, value);
    }
  }
}
