import { getContext, setContext } from 'svelte';
import type { DragDropState } from '@thisux/sveltednd';

const CTX = Symbol('sortable-list');

export class SortableListState<T> {
	items = $state<T[]>([]);
	key: (item: T) => string = () => '';
	onReorder: (reordered: T[]) => void = () => {};
	debounceMs = 250;
	#lastReorderAt = 0;

	sync(newItems: T[]) {
		this.items = [...newItems];
	}

	containerOf(item: T): string {
		return `sortable:${this.key(item)}`;
	}

	handleDragEnter = (state: DragDropState<T>) => {
		const now = Date.now();
		if (now - this.#lastReorderAt < this.debounceMs) return;

		const { draggedItem, targetContainer } = state;
		if (!targetContainer?.startsWith('sortable:')) return;

		const targetKey = targetContainer.slice('sortable:'.length);
		const draggedKey = this.key(draggedItem);
		if (draggedKey === targetKey) return;

		const fromIdx = this.items.findIndex((i) => this.key(i) === draggedKey);
		const toIdx = this.items.findIndex((i) => this.key(i) === targetKey);
		if (fromIdx === -1 || toIdx === -1) return;

		const [moved] = this.items.splice(fromIdx, 1);
		this.items.splice(toIdx, 0, moved);
		this.#lastReorderAt = now;
	};

	handleDrop = (_state: DragDropState<T>) => {
		this.onReorder(this.items);
	};
}

export function setSortableListContext<T>(state: SortableListState<T>) {
	setContext(CTX, state);
}

export function getSortableListContext<T>(): SortableListState<T> {
	return getContext<SortableListState<T>>(CTX);
}
