<!-- TODO: This component needs to be updated for the new Stage/App architecture -->
<div class="flex h-64 items-center justify-center rounded border border-zinc-700">
	<p class="text-sm text-zinc-500">Stage canvas - update pending...</p>
</div>

<!--
ORIGINAL COMPONENT - Commented out for reference during refactor

<script lang="ts">
	import type { Stage } from './stage.svelte.ts';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	// Derived data from stage
	let stageConfig = $derived(stage.config);
	let xAxis = $derived(stage.xAxis);
	let yAxis = $derived(stage.yAxis);
	let zAxis = $derived(stage.zAxis);
	let stageWidth = $derived(stage.stageWidth);
	let stageHeight = $derived(stage.stageHeight);
	let stageDepth = $derived(stage.stageDepth);
	let fov = $derived(stage.fov);
	let thumbnail = $derived(stage.thumbnail);
	let zRange = $derived(stage.zRange);
	let numGridCellsX = $derived(stage.gridConfig.numCellsX);
	let numGridCellsY = $derived(stage.gridConfig.numCellsY);
	let gridOriginX = $derived(stage.gridConfig.originX);
	let gridOriginY = $derived(stage.gridConfig.originY);
	let gridSpacingX = $derived(stage.gridSpacingX);
	let gridSpacingY = $derived(stage.gridSpacingY);

	// Handle grid cell click
	function handleGridCellClick(i: number, j: number) {
		stage.moveToGridCell(i, j);
	}

	// Handle slider changes
	function handleXSliderChange(e: Event) {
		if (!xAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		xAxis.move(position);
	}

	function handleYSliderChange(e: Event) {
		if (!yAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		yAxis.move(position);
	}

	function handleZSliderChange(e: Event) {
		if (!zAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		zAxis.move(position);
	}

	let gridCellClass = $derived(
		xAxis?.isMoving || yAxis?.isMoving
			? 'cursor-not-allowed stroke-zinc-600 fill-zinc-800/40'
			: 'cursor-pointer stroke-zinc-500 fill-zinc-800/50 hover:fill-zinc-700/30'
	);

	let isXYMoving = $derived(xAxis?.isMoving || yAxis?.isMoving);
	let fovStrokeColor = $derived(isXYMoving ? '#e11d48' : '#10b981');
	let fovFillColor = $derived(isXYMoving ? 'var(- -color-rose-600/50)' : 'var(- -color-emerald-600/50)');
</script>

{#snippet zMarker(label: string, position: number, strokeClass: string)}
	<g>
		<title>{label}: {position.toFixed(1)} mm</title>
		<line
			x1="0"
			y1={stageDepth - (position - (zAxis?.lowerLimit ?? 0))}
			x2="30"
			y2={stageDepth - (position - (zAxis?.lowerLimit ?? 0))}
			stroke-width="0.2"
			opacity="1"
			class={strokeClass}
		/>
	</g>
{/snippet}

{#if stageConfig && xAxis && yAxis && zAxis}
	<div class="flex items-center" style={`aspect-ratio: ${fov.w / fov.h};`}>
		<div class="stage-grid relative w-full">
			<div class="absolute top-2 right-4 px-2 text-right font-mono text-[0.65rem] text-zinc-400">
				{stageWidth.toFixed(0)} x {stageHeight.toFixed(0)} x {stageDepth.toFixed(0)} mm
			</div>
			... (rest of template)
		</div>
	</div>
{/if}

<style>
	.stage-grid {
		- -track-width: 0.75rem;
		- -thumb-width: 2px;
		- -area-bg: rgb(24 24 27);
		display: grid;
		grid-template-columns: auto 1fr auto;
		grid-template-rows: auto auto auto;
		gap: calc(-1 * var(- -track-width));
		margin: calc(-0.5 * var(- -track-width));
		margin-block-start: 0;
		margin-inline-end: 0;
	}
	... (rest of styles)
</style>
-->
