import { SvelteSet } from 'svelte/reactivity';

export interface MultiSelect<K> {
	/** The set of selected keys. */
	readonly selection: SvelteSet<K>;
	/** The last-clicked key (drives detail/preview views). */
	readonly focused: K | null;
	/** Number of selected items. */
	readonly size: number;
	/** Plain click: single-select + focus. */
	select(key: K): void;
	/** Ctrl/Cmd+click: toggle item in/out of selection + focus. */
	toggle(key: K): void;
	/** Shift+click: range-select from focused to target + focus. */
	rangeSelect(key: K): void;
	/** Select a specific set of keys. */
	selectAll(keys: K[]): void;
	/** Check if a key is selected. */
	has(key: K): boolean;
	/** Deselect all. */
	clear(): void;
	/** Focus a key without changing selection. */
	focus(key: K): void;
}

/**
 * Creates a reactive multi-select state manager.
 *
 * @param getKeys - Returns the current ordered list of selectable keys.
 *                  Called on each `rangeSelect` to determine the range.
 */
export function createMultiSelect<K>(getKeys: () => K[]): MultiSelect<K> {
	const selection = new SvelteSet<K>();
	let focused = $state<K | null>(null);

	return {
		get selection() {
			return selection;
		},
		get focused() {
			return focused;
		},
		get size() {
			return selection.size;
		},

		select(key: K) {
			selection.clear();
			selection.add(key);
			focused = key;
		},

		toggle(key: K) {
			if (selection.has(key)) {
				selection.delete(key);
			} else {
				selection.add(key);
			}
			focused = key;
		},

		rangeSelect(key: K) {
			if (focused === null) {
				selection.clear();
				selection.add(key);
				focused = key;
				return;
			}
			const keys = getKeys();
			const from = keys.indexOf(focused);
			const to = keys.indexOf(key);
			if (from === -1 || to === -1) {
				selection.clear();
				selection.add(key);
				focused = key;
				return;
			}
			const start = Math.min(from, to);
			const end = Math.max(from, to);
			for (let i = start; i <= end; i++) {
				selection.add(keys[i]);
			}
			focused = key;
		},

		selectAll(keys: K[]) {
			selection.clear();
			for (const key of keys) selection.add(key);
		},

		has(key: K) {
			return selection.has(key);
		},

		clear() {
			selection.clear();
			focused = null;
		},

		focus(key: K) {
			focused = key;
		}
	};
}
