<script lang="ts">
	import type { Stage } from './stage.svelte.ts';
	import DraggableNumberInput from '$lib/ui/DraggableNumberInput.svelte';

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
</script>

{#if xAxis && yAxis && zAxis}
	<div class="flex flex-col gap-4 p-4 pb-4">
		<!-- Grid controls -->
		<div class="grid grid-cols-[auto_auto_auto] items-center gap-x-2 gap-y-1 text-xs text-zinc-400">
			<span class="col-span-3 text-sm font-medium text-zinc-500">Grid</span>

			<span class="text-[0.65rem] text-zinc-500">Origin</span>
			<DraggableNumberInput
				bind:value={gridConfig.originX}
				min={0}
				max={stageWidth}
				step={0.5}
				decimals={1}
				numCharacters={4}
				showButtons={true}
			/>
			<DraggableNumberInput
				bind:value={gridConfig.originY}
				min={0}
				max={stageHeight}
				step={0.5}
				decimals={1}
				numCharacters={4}
				showButtons={true}
			/>

			<!-- Grid cells -->
			<span class="text-[0.65rem] text-zinc-500">Cells</span>
			<DraggableNumberInput
				bind:value={gridConfig.numCellsX}
				min={1}
				max={maxGridCellsX}
				step={1}
				decimals={0}
				numCharacters={3}
				showButtons={true}
			/>
			<DraggableNumberInput
				bind:value={gridConfig.numCellsY}
				min={1}
				max={maxGridCellsY}
				step={1}
				decimals={0}
				numCharacters={3}
				showButtons={true}
			/>

			<!-- Overlap -->
			<span class="text-[0.65rem] text-zinc-500">Overlap</span>
			<div class="col-span-2 flex items-center gap-2">
				<DraggableNumberInput
					bind:value={gridConfig.overlap}
					min={0}
					max={0.5}
					step={0.05}
					decimals={2}
					numCharacters={4}
					showButtons={true}
				/>
				<span class="text-zinc-600">%</span>
			</div>
		</div>
	</div>
{/if}
