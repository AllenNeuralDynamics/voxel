import { SvelteMap } from 'svelte/reactivity';

import type { StateMessage } from './client.svelte';

/** The last value of each feed topic. Reading 1 topic tracks only that topic. Only the Client writes. */
export class Topics {
  readonly #cells: SvelteMap<string, unknown>;
  readonly #prefix: string;

  constructor(cells = new SvelteMap<string, unknown>(), prefix = '') {
    this.#cells = cells;
    this.#prefix = prefix;
  }

  /** A read-only store. */
  static of(values: Record<string, unknown>): Topics {
    return new Topics(new SvelteMap(Object.entries(values)));
  }

  get<T>(name: string): T | undefined {
    return this.#cells.get(this.#prefix + name) as T | undefined;
  }

  has(name: string): boolean {
    return this.#cells.has(this.#prefix + name);
  }

  /** The next name part under `prefix`, in arrival order. Changes only when a topic is added or removed. */
  names(prefix = ''): string[] {
    const start = prefix ? `${this.#prefix}${prefix}.` : this.#prefix;
    const found = new Set<string>();
    for (const key of this.#cells.keys()) {
      if (key.startsWith(start)) found.add(key.slice(start.length).split('.', 1)[0]);
    }
    return [...found];
  }

  scope(prefix: string): Topics {
    return new Topics(this.#cells, `${this.#prefix}${prefix}.`);
  }

  /** A full message also removes every topic it does not name. */
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
