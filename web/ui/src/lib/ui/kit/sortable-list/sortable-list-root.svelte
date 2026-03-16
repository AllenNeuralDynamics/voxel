<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { flip } from 'svelte/animate';
	import { SortableListState, setSortableListContext } from './sortable-list.svelte';

	interface Props {
		items: T[];
		key: (item: T) => string;
		onReorder: (reordered: T[]) => void;
		item: Snippet<[T, number]>;
		class?: string;
		flipDuration?: number;
		debounceMs?: number;
	}

	let { items, key, onReorder, item, class: className = '', flipDuration = 200, debounceMs = 250 }: Props = $props();

	const state = new SortableListState<T>();
	setSortableListContext(state);

	$effect(() => {
		state.sync(items);
		state.key = key;
		state.onReorder = onReorder;
		state.debounceMs = debounceMs;
	});
</script>

<div class={className}>
	{#each state.items as entry, i (state.key(entry))}
		<div animate:flip={{ duration: flipDuration }}>
			{@render item(entry, i)}
		</div>
	{/each}
</div>
