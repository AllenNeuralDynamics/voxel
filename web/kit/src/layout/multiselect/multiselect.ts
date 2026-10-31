/** The rules of a multiselect, with no Svelte, so tests can run them. `multiselect.svelte.ts` keeps the live pick. */

/** `anchor` is the item a range starts from. */
export interface Pick<K> {
  readonly picked: ReadonlySet<K>;
  readonly focus: K | null;
  readonly anchor: K | null;
}

/** `next` and `previous` move the focus only. */
export type PickAction = 'only' | 'solo' | 'toggle' | 'range' | 'span' | 'all' | 'next' | 'previous';

/**
 * How a click works. `select` is like a file list: a click picks only the item, and Cmd+click adds or removes it.
 * `toggle` is like checkboxes: a click turns the item on or off, and a double-click picks only the item.
 */
export type ClickMode = 'select' | 'toggle';

interface Modifiers {
  shiftKey: boolean;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
}

export function only<K>(key: K): Pick<K> {
  return { picked: new Set([key]), focus: key, anchor: key };
}

/** Picks only `key`, or all items when `key` is already the only pick, so the same action goes back. */
export function solo<K>(pick: Pick<K>, keys: readonly K[], key: K): Pick<K> {
  const alone = pick.picked.size === 1 && pick.picked.has(key);
  return alone ? { picked: new Set(keys), focus: key, anchor: key } : only(key);
}

export function toggle<K>(pick: Pick<K>, key: K): Pick<K> {
  const picked = new Set(pick.picked);
  if (!picked.delete(key)) picked.add(key);
  return { picked, focus: key, anchor: key };
}

/** Picks the items from the anchor to `key`, and drops the others. Without an anchor in `keys`, it picks only `key`. */
export function range<K>(pick: Pick<K>, keys: readonly K[], key: K): Pick<K> {
  const from = pick.anchor === null ? -1 : keys.indexOf(pick.anchor);
  const to = keys.indexOf(key);
  if (from === -1 || to === -1) return only(key);
  const picked = new Set(keys.slice(Math.min(from, to), Math.max(from, to) + 1));
  return { picked, focus: key, anchor: pick.anchor };
}

/**
 * Gives the items from the anchor to `key` the new state of `key`, as Shift+click does on checkboxes in Gmail. The
 * other items stay. Without an anchor in `keys`, it turns only `key` on or off.
 */
export function span<K>(pick: Pick<K>, keys: readonly K[], key: K): Pick<K> {
  const from = pick.anchor === null ? -1 : keys.indexOf(pick.anchor);
  const to = keys.indexOf(key);
  if (from === -1 || to === -1) return toggle(pick, key);
  const on = !pick.picked.has(key);
  const picked = new Set(pick.picked);
  for (const item of keys.slice(Math.min(from, to), Math.max(from, to) + 1)) {
    if (on) picked.add(item);
    else picked.delete(item);
  }
  return { picked, focus: key, anchor: key };
}

export function all<K>(pick: Pick<K>, keys: readonly K[]): Pick<K> {
  return { ...pick, picked: new Set(keys) };
}

export function none<K>(pick: Pick<K>): Pick<K> {
  return { ...pick, picked: new Set() };
}

/** Moves the focus 1 item from `key`, stopping at the first and the last item. */
export function move<K>(pick: Pick<K>, keys: readonly K[], key: K, step: 1 | -1): Pick<K> {
  if (!keys.length) return pick;
  const index = keys.indexOf(key);
  const next = index === -1 ? (step === 1 ? 0 : keys.length - 1) : Math.min(keys.length - 1, Math.max(0, index + step));
  return { ...pick, focus: keys[next] };
}

export function act<K>(pick: Pick<K>, action: PickAction, keys: readonly K[], key: K): Pick<K> {
  switch (action) {
    case 'only':
      return only(key);
    case 'solo':
      return solo(pick, keys, key);
    case 'toggle':
      return toggle(pick, key);
    case 'range':
      return range(pick, keys, key);
    case 'span':
      return span(pick, keys, key);
    case 'all':
      return all(pick, keys);
    case 'next':
      return move(pick, keys, key, 1);
    case 'previous':
      return move(pick, keys, key, -1);
  }
}

/**
 * The action of a click. `mac` makes Cmd, not Ctrl, the key that adds or removes 1 item. `detail` counts the clicks
 * in a row: 2 is the second click of a double-click.
 */
export function clickAction(
  event: Modifiers & { detail: number },
  mac: boolean,
  mode: ClickMode = 'select'
): 'only' | 'solo' | 'toggle' | 'range' | 'span' {
  if (mode === 'toggle') {
    if (event.shiftKey) return 'span';
    return event.detail === 2 ? 'solo' : 'toggle';
  }
  if (event.shiftKey) return 'range';
  return (mac ? event.metaKey : event.ctrlKey) ? 'toggle' : 'only';
}

export function keyAction(
  event: Modifiers & { key: string },
  mac: boolean,
  mode: ClickMode = 'select'
): PickAction | null {
  const mod = mac ? event.metaKey : event.ctrlKey;
  const other = mac ? event.ctrlKey : event.metaKey;
  if (event.altKey || other) return null;
  if (mod) return event.key.toLowerCase() === 'a' && !event.shiftKey ? 'all' : null;
  if (event.key === ' ') {
    if (!event.shiftKey) return 'toggle';
    return mode === 'toggle' ? 'span' : 'range';
  }
  if (event.shiftKey) return null;
  if (event.key === 'ArrowDown') return 'next';
  if (event.key === 'ArrowUp') return 'previous';
  if (event.key === 'Enter') return mode === 'toggle' ? 'solo' : 'only';
  return null;
}

export function same<K>(a: ReadonlySet<K>, b: ReadonlySet<K>): boolean {
  return a.size === b.size && [...a].every((key) => b.has(key));
}

/** Picks that are no longer in `keys` drop out. */
export function ordered<K>(keys: readonly K[], picked: ReadonlySet<K>): K[] {
  return keys.filter((key) => picked.has(key));
}

export function pickState<K>(keys: readonly K[], picked: ReadonlySet<K>): 'all' | 'some' | 'none' {
  const count = keys.filter((key) => picked.has(key)).length;
  return count === 0 ? 'none' : count === keys.length ? 'all' : 'some';
}
