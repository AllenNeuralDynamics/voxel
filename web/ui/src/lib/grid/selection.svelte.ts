/** Shared selection of acquisition tasks, by id. Provided once by the (v2) layout and consumed by the
 *  GridCanvas planes and the plan-page table so the two stay in sync. View-layer state — not on `Instrument`. */
import { getContext, setContext } from 'svelte';
import { SvelteSet } from 'svelte/reactivity';

export class TaskSelection {
  readonly ids = new SvelteSet<string>();

  has(id: string): boolean {
    return this.ids.has(id);
  }

  get size(): number {
    return this.ids.size;
  }

  get list(): string[] {
    return [...this.ids];
  }

  /** Select exactly one task, replacing any prior selection. */
  select(id: string): void {
    this.ids.clear();
    this.ids.add(id);
  }

  toggle(id: string): void {
    if (!this.ids.delete(id)) this.ids.add(id);
  }

  add(...ids: string[]): void {
    for (const id of ids) this.ids.add(id);
  }

  clear(): void {
    this.ids.clear();
  }
}

const KEY = Symbol('task-selection');

/** Create the shared selection and publish it on context. Call once, in the layout. */
export function provideTaskSelection(): TaskSelection {
  const selection = new TaskSelection();
  setContext(KEY, selection);
  return selection;
}

/** Read the shared selection (provided by the layout). */
export function getTaskSelection(): TaskSelection {
  return getContext(KEY);
}
