<script lang="ts">
	import type { App } from '$lib/app';
	import SpinBox from '$lib/ui/primitives/SpinBox.svelte';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get stage and config from app
	let stage = $derived(app.stage);
	let gridConfig = $derived(app.gridConfig);
	let gridLocked = $derived(app.gridLocked);
	let layerVisibility = $derived(app.layerVisibility);

	// Grid offset in mm for display (stored in μm)
	let gridOffsetXMm = $derived(gridConfig.x_offset_um / 1000);
	let gridOffsetYMm = $derived(gridConfig.y_offset_um / 1000);

	// Update grid offset (convert mm to μm)
	function updateGridOffsetX(value: number) {
		if (gridLocked) return;
		app.setGridOffset(value * 1000, gridConfig.y_offset_um);
	}

	function updateGridOffsetY(value: number) {
		if (gridLocked) return;
		app.setGridOffset(gridConfig.x_offset_um, value * 1000);
	}

	function updateGridOverlap(value: number) {
		if (gridLocked) return;
		app.setGridOverlap(value);
	}

	// Toggle layer visibility
	function toggleGrid() {
		app.layerVisibility = { ...layerVisibility, grid: !layerVisibility.grid };
	}

	function toggleStacks() {
		app.layerVisibility = { ...layerVisibility, stacks: !layerVisibility.stacks };
	}

	function toggleFov() {
		app.layerVisibility = { ...layerVisibility, fov: !layerVisibility.fov };
	}
</script>

{#if stage}
	<div class="flex flex-wrap items-center gap-4 border-t border-zinc-800 px-4 py-3 text-xs text-zinc-400">
		<!-- Layer visibility toggles -->
		<div class="flex items-center gap-3">
			<span class="text-[0.65rem] text-zinc-500">Layers:</span>
			<label class="flex cursor-pointer items-center gap-1">
				<input
					type="checkbox"
					checked={layerVisibility.grid}
					onchange={toggleGrid}
					class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
				/>
				<span>Grid</span>
			</label>
			<label class="flex cursor-pointer items-center gap-1">
				<input
					type="checkbox"
					checked={layerVisibility.stacks}
					onchange={toggleStacks}
					class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
				/>
				<span>Stacks</span>
			</label>
			<label class="flex cursor-pointer items-center gap-1">
				<input
					type="checkbox"
					checked={layerVisibility.fov}
					onchange={toggleFov}
					class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
				/>
				<span>FOV</span>
			</label>
		</div>

		<div class="h-4 w-px bg-zinc-700"></div>

		<!-- Grid offset controls -->
		<div class="flex items-center gap-2" class:opacity-50={gridLocked} class:pointer-events-none={gridLocked}>
			<span class="text-[0.65rem] text-zinc-500">Offset:</span>
			<SpinBox
				value={gridOffsetXMm}
				onChange={updateGridOffsetX}
				min={0}
				max={stage.width}
				step={0.1}
				decimals={1}
				numCharacters={4}
				showButtons={true}
			/>
			<SpinBox
				value={gridOffsetYMm}
				onChange={updateGridOffsetY}
				min={0}
				max={stage.height}
				step={0.1}
				decimals={1}
				numCharacters={4}
				showButtons={true}
			/>
			<span class="text-[0.65rem] text-zinc-600">mm</span>
		</div>

		<div class="h-4 w-px bg-zinc-700"></div>

		<!-- Overlap control -->
		<div class="flex items-center gap-2" class:opacity-50={gridLocked} class:pointer-events-none={gridLocked}>
			<span class="text-[0.65rem] text-zinc-500">Overlap:</span>
			<SpinBox
				value={gridConfig.overlap}
				onChange={updateGridOverlap}
				min={0}
				max={0.5}
				step={0.05}
				decimals={2}
				numCharacters={4}
				showButtons={true}
			/>
		</div>

		{#if gridLocked}
			<span class="text-[0.65rem] text-amber-500">Grid locked (stacks planned)</span>
		{/if}
	</div>
{/if}
