<script lang="ts">
	import { Stage } from '$lib/app';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	export function formatPosition(position: number | null): string {
		if (position === null) return '---';
		const formatted = Math.abs(position).toFixed(2);
		return position >= 0 ? `+${formatted}` : `-${formatted}`;
	}
	// Check if any axis is moving
	let isAnyAxisMoving = $derived(stage.isMoving);
</script>

<div class="flex items-center gap-3 font-mono text-xs">
	<span class="text-zinc-500">Stage:</span>

	<!-- X Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">X:</span>
		<span class={stage.x.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(stage.x.position)}</span>
	</div>

	<!-- Y Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">Y:</span>
		<span class={stage.y.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(stage.y.position)}</span>
	</div>

	<!-- Z Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">Z:</span>
		<span class={stage.z.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(stage.z.position)}</span>
	</div>

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
