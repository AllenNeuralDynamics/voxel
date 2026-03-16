<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { draggable, droppable } from '@thisux/sveltednd';
	import { getSortableListContext } from './sortable-list.svelte';

	interface Props {
		item: T;
		children: Snippet;
		class?: string;
	}

	let { item, children, class: className = '' }: Props = $props();

	const state = getSortableListContext<T>();
</script>

<div
	use:draggable={{ container: state.containerOf(item), dragData: item }}
	use:droppable={{
		container: state.containerOf(item),
		callbacks: { onDragEnter: state.handleDragEnter, onDrop: state.handleDrop }
	}}
	class={className}
>
	{@render children()}
</div>
