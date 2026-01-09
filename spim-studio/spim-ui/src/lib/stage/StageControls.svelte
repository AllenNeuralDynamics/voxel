<script lang="ts">
	import type { Stage } from './stage.svelte.ts';
	import SpinBox from '$lib/ui/SpinBox.svelte';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	// Derived data from stage
	let xAxis = $derived(stage.xAxis);
	let yAxis = $derived(stage.yAxis);
	let zAxis = $derived(stage.zAxis);
	let stageWidth = $derived(stage.stageWidth);
	let stageHeight = $derived(stage.stageHeight);
	let maxGridCellsX = $derived(stage.maxGridCellsX);
	let maxGridCellsY = $derived(stage.maxGridCellsY);

	// Direct access to stage grid config for two-way binding
	let gridConfig = $derived(stage.gridConfig);
	let zRange = $derived(stage.zRange);
</script>

{#if xAxis && yAxis && zAxis}
	<div
		class="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 p-4 text-xs text-zinc-400"
	>
		<!-- Z-Range controls -->
		<!-- <span class="col-span-full text-sm font-medium text-zinc-500">Z</span> -->
		<span class="text-[0.65rem] text-zinc-500">Z-Range</span>
		<SpinBox
			bind:value={zRange.min}
			min={zAxis.lowerLimit}
			max={zRange.max}
			step={0.5}
			decimals={1}
			numCharacters={5}
			showButtons={true}
		/>
		<SpinBox
			bind:value={zRange.max}
			min={zRange.min}
			max={zAxis.upperLimit}
			step={0.5}
			decimals={1}
			numCharacters={5}
			showButtons={true}
		/>
		<span></span>

		<!-- Grid controls -->
		<span class="col-span-full pt-2 text-sm font-medium text-zinc-500"></span>

		<span class="text-[0.65rem] text-zinc-500">Grid Origin</span>
		<SpinBox
			bind:value={gridConfig.originX}
			min={0}
			max={stageWidth}
			step={0.5}
			decimals={1}
			numCharacters={4}
			showButtons={true}
		/>
		<SpinBox
			bind:value={gridConfig.originY}
			min={0}
			max={stageHeight}
			step={0.5}
			decimals={1}
			numCharacters={4}
			showButtons={true}
		/>
		<span></span>

		<!-- Grid cells -->
		<span class="text-[0.65rem] text-zinc-500">Grid Cells</span>
		<SpinBox
			bind:value={gridConfig.numCellsX}
			min={1}
			max={maxGridCellsX}
			step={1}
			decimals={0}
			numCharacters={3}
			showButtons={true}
		/>
		<SpinBox
			bind:value={gridConfig.numCellsY}
			min={1}
			max={maxGridCellsY}
			step={1}
			decimals={0}
			numCharacters={3}
			showButtons={true}
		/>
		<span></span>

		<!-- Overlap -->
		<span class="text-[0.65rem] text-zinc-500">Grid Overlap</span>
		<SpinBox
			bind:value={gridConfig.overlap}
			min={0}
			max={0.5}
			step={0.05}
			decimals={2}
			numCharacters={4}
			showButtons={true}
			classNames="col-span-2"
		/>
		<span class="text-zinc-500">%</span>
	</div>
{/if}
