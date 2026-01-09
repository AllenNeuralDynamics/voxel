<script lang="ts">
	import type { Stage } from './stage.svelte.ts';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	// Derived axis data
	let xAxis = $derived(stage.xAxis);
	let yAxis = $derived(stage.yAxis);
	let zAxis = $derived(stage.zAxis);

	// Check if any axis is moving
	let isAnyAxisMoving = $derived(xAxis?.isMoving || yAxis?.isMoving || zAxis?.isMoving);

	// Format position with explicit sign
	function formatPosition(position: number | null): string {
		if (position === null) return '---';
		const formatted = Math.abs(position).toFixed(2);
		return position >= 0 ? `+${formatted}` : `-${formatted}`;
	}
</script>

<div class="flex items-center gap-3 font-mono text-xs">
	<span class="text-zinc-500">Stage:</span>

	<!-- X Axis -->
	{#if xAxis}
		<div class="flex items-center gap-1.5">
			<span class="text-zinc-500">X:</span>
			<span class={xAxis.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(xAxis.position)}</span>
		</div>
	{/if}

	<!-- Y Axis -->
	{#if yAxis}
		<div class="flex items-center gap-1.5">
			<span class="text-zinc-500">Y:</span>
			<span class={yAxis.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(yAxis.position)}</span>
		</div>
	{/if}

	<!-- Z Axis -->
	{#if zAxis}
		<div class="flex items-center gap-1.5">
			<span class="text-zinc-500">Z:</span>
			<span class={zAxis.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(zAxis.position)}</span>
		</div>
	{/if}

	<!-- Halt button -->
	<button
		onclick={() => stage.halt()}
		disabled={!isAnyAxisMoving}
		class="ml-2 rounded border px-2 py-0.5 text-xs transition-colors {isAnyAxisMoving
			? 'border-rose-500 bg-rose-500 text-white hover:cursor-pointer hover:border-rose-600 hover:bg-rose-600'
			: 'cursor-not-allowed border-zinc-700 text-zinc-500'}"
	>
		Halt
	</button>
</div>
