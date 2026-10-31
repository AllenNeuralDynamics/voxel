import { onDestroy, untrack } from 'svelte';
import type { Attachment } from 'svelte/attachments';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import { reportFailure } from '../../failures';
import { heldKey, isMac } from './held-key.svelte';
import {
  act,
  all,
  clickAction,
  type ClickMode,
  keyAction,
  none,
  ordered,
  type Pick,
  type PickAction,
  pickState,
  same
} from './multiselect';

/** How long a saved pick shows while the page still shows the old one. */
const SETTLE_MS = 1000;
/** How long a click in `toggle` mode waits for a second click, so that a double-click saves 1 pick, not 2. */
const DOUBLE_CLICK_MS = 300;

export interface MultiSelectOptions<K> {
  keys: () => readonly K[];
  /** The saved pick, for example a list on the server. It shows while you do not pick. */
  saved: () => readonly K[];
  /** Saves a finished pick, in item order. While it runs, newer picks wait, and only the last one is saved next. */
  save: (picked: K[]) => unknown;
  /** No picks while it is true, for example during a run. */
  disabled?: () => boolean;
  /** `select` by default. */
  mode?: ClickMode;
}

/**
 * Picks items from a list. On an item, ↑ and ↓ move, Space adds or removes it, and Cmd+A (Ctrl+A) picks all.
 *
 * - `select` mode, like a file list: a click picks only the item, Cmd+click (Ctrl+click) adds or removes it, and
 *   Shift+click picks a range. Enter picks only the item, and Shift+Space picks a range. Cmd+clicks are saved when
 *   Cmd goes up.
 * - `toggle` mode, like checkboxes: a click adds or removes the item, a double-click picks only it (or all, when it is
 *   the only pick), and Shift+click gives the items from the last click to it the new state of the item. Enter acts
 *   like a double-click, and Shift+Space like Shift+click. A click is saved after a short wait for a second click.
 *
 * Other picks are saved at once. Create it while the component starts.
 */
export class MultiSelect<K> {
  /** The key that adds or removes 1 item in `select` mode, for hints. */
  readonly modKey = isMac ? '⌘' : 'Ctrl';

  readonly #options: MultiSelectOptions<K>;
  readonly #mode: ClickMode;
  readonly #mod = heldKey(isMac ? 'Meta' : 'Control');
  readonly #elements = new SvelteMap<K, HTMLElement>();
  #focus = $state<K | null>(null);
  #anchor = $state<K | null>(null);
  // A pick that is not saved yet. It is open while Cmd is down or a click waits for a second one. Then it is finished,
  // and it can wait for a save to end.
  #draft = $state.raw<ReadonlySet<K> | null>(null);
  #open = $state(false);
  #saving = $state.raw<ReadonlySet<K> | null>(null);
  // The last saved pick, and the saved list that it replaced. It shows until that list changes.
  #sent = $state.raw<{ picked: ReadonlySet<K>; replaced: ReadonlySet<K> } | null>(null);
  #settleTimer: ReturnType<typeof setTimeout> | undefined;
  #clickTimer: ReturnType<typeof setTimeout> | undefined;
  // The pick from before the first click of a double-click.
  #beforeClick: Pick<K> | null = null;

  readonly #saved = $derived.by(() => new SvelteSet(this.#options.saved()));
  readonly #settled = $derived(this.#sent && same(this.#saved, this.#sent.replaced) ? this.#sent.picked : this.#saved);
  readonly #shown = $derived(this.#draft ?? this.#saving ?? this.#settled);
  // The 1 item that Tab goes to: the focus, else the first picked item, else the first item.
  readonly #tabTarget = $derived.by(() => {
    const keys = this.#options.keys();
    if (this.#focus !== null && keys.includes(this.#focus)) return this.#focus;
    return keys.find((key) => this.#shown.has(key)) ?? keys[0];
  });

  constructor(options: MultiSelectOptions<K>) {
    this.#options = options;
    this.#mode = options.mode ?? 'select';
    // Cmd going up finishes the Cmd+clicks.
    $effect(() => {
      if (!this.#mod.held) untrack(() => this.#finish());
    });
    onDestroy(() => {
      clearTimeout(this.#settleTimer);
      clearTimeout(this.#clickTimer);
    });
  }

  /** The pick that shows: yours while you pick and while it saves, else the saved one. */
  get picked(): ReadonlySet<K> {
    return this.#shown;
  }

  get state(): 'all' | 'some' | 'none' {
    return pickState(this.#options.keys(), this.#shown);
  }

  get count(): number {
    return ordered(this.#options.keys(), this.#shown).length;
  }

  /** A pick waits or saves. */
  get pending(): boolean {
    return this.#saving !== null || (this.#draft !== null && !this.#open);
  }

  get disabled(): boolean {
    return this.#options.disabled?.() ?? false;
  }

  has(key: K): boolean {
    return this.#shown.has(key);
  }

  /** The items are 1 stop for Tab. The arrow keys move between them. */
  tabIndex(key: K): 0 | -1 {
    return key === this.#tabTarget ? 0 : -1;
  }

  /** The element of an item, so the arrow keys can move the focus to it. */
  element(key: K): Attachment<HTMLElement> {
    return (node) => {
      this.#elements.set(key, node);
      return () => {
        if (this.#elements.get(key) === node) this.#elements.delete(key);
      };
    };
  }

  click(key: K, event: MouseEvent): void {
    // A click from Enter or Space has no pointer. `keydown` did its work.
    if (event.detail === 0 || this.disabled) return;
    const action = clickAction(event, isMac, this.#mode);
    if (this.#mode === 'select') {
      // Cmd+clicks wait for Cmd to go up. If the page did not see Cmd go down, the pick is finished at once.
      this.#apply(action, key, action !== 'toggle' || !this.#mod.held);
    } else if (action === 'solo') {
      // The second click of a double-click works on the pick from before the first click.
      this.#apply(action, key, true, this.#beforeClick ?? this.#pick());
    } else if (action !== 'toggle') {
      this.#apply(action, key, true);
    } else if (event.detail === 1) {
      // The box changes at once. The save waits for a second click.
      this.#beforeClick = this.#pick();
      this.#apply(action, key, false);
      this.#clickTimer = setTimeout(() => this.#finish(), DOUBLE_CLICK_MS);
    }
  }

  keydown(key: K, event: KeyboardEvent): void {
    if (event.isComposing) return;
    const action = keyAction(event, isMac, this.#mode);
    if (!action) return;
    event.preventDefault();
    if (action === 'next' || action === 'previous') {
      const next = act(this.#pick(), action, this.#options.keys(), key);
      this.#focus = next.focus;
      if (next.focus !== null) this.#elements.get(next.focus)?.focus();
    } else if (!this.disabled) {
      this.#apply(action, key, true);
    }
  }

  /** Picks all items, or none. */
  setAll(on: boolean): void {
    if (this.disabled) return;
    const next = on ? all(this.#pick(), this.#options.keys()) : none(this.#pick());
    this.#draft = next.picked;
    this.#open = false;
    clearTimeout(this.#clickTimer);
    void this.#flush();
  }

  #pick(): Pick<K> {
    return { picked: this.#shown, focus: this.#focus, anchor: this.#anchor };
  }

  #apply(action: PickAction, key: K, finished: boolean, base = this.#pick()): void {
    const next = act(base, action, this.#options.keys(), key);
    this.#focus = next.focus;
    this.#anchor = next.anchor;
    this.#draft = next.picked;
    this.#open = !finished;
    clearTimeout(this.#clickTimer);
    if (finished) void this.#flush();
  }

  #finish(): void {
    if (!this.#open) return;
    this.#open = false;
    void this.#flush();
  }

  /** Saves the waiting pick, unless a save runs. That save saves it when it ends, so the last pick wins. */
  async #flush(): Promise<void> {
    const picked = this.#draft;
    if (picked === null || this.#open || this.#saving !== null) return;
    this.#draft = null;
    if (same(picked, this.#settled)) return;
    const replaced = this.#saved;
    this.#saving = picked;
    clearTimeout(this.#settleTimer);
    try {
      await this.#options.save(ordered(this.#options.keys(), picked));
      this.#sent = { picked, replaced };
      this.#settleTimer = setTimeout(() => (this.#sent = null), SETTLE_MS);
    } catch (error) {
      reportFailure(error);
      this.#sent = null;
    } finally {
      this.#saving = null;
      void this.#flush();
    }
  }
}
