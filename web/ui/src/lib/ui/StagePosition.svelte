<script lang="ts">
	import type { App } from '$lib/app';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get axes from app
	let xAxis = $derived(app.xAxis);
	let yAxis = $derived(app.yAxis);
	let zAxis = $derived(app.zAxis);

	export function formatPosition(position: number | null | undefined): string {
		if (position === null || position === undefined) return '---';
		const formatted = Math.abs(position).toFixed(2);
		return position >= 0 ? `+${formatted}` : `-${formatted}`;
	}

	// Check if any axis is moving
	let isAnyAxisMoving = $derived(app.stageIsMoving);
</script>

<div class="flex items-center gap-3 font-mono text-xs">
	<span class="text-zinc-500">Stage:</span>

	<!-- X Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">X:</span>
		<span class={xAxis?.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(xAxis?.position)}</span>
	</div>

	<!-- Y Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">Y:</span>
		<span class={yAxis?.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(yAxis?.position)}</span>
	</div>

	<!-- Z Axis -->
	<div class="flex items-center gap-1.5">
		<span class="text-zinc-500">Z:</span>
		<span class={zAxis?.isMoving ? 'text-rose-500' : 'text-zinc-300'}>{formatPosition(zAxis?.position)}</span>
	</div>

	<!-- Halt button -->
	<button
		onclick={() => app.haltStage()}
		disabled={!isAnyAxisMoving}
		class="ml-2 rounded border px-2 py-0.5 text-xs transition-colors {isAnyAxisMoving
			? 'border-rose-500 bg-rose-500 text-white hover:cursor-pointer hover:border-rose-600 hover:bg-rose-600'
			: 'cursor-not-allowed border-zinc-700 text-zinc-500'}"
	>
		Halt
	</button>
</div>
