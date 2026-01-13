<script lang="ts">
	import type { App } from '$lib/app';
	import { getStackStatusColor, type Tile, type Stack } from '$lib/core/types';
	import { onMount } from 'svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Computed derived state (not simple aliases)
	let fovX = $derived(app.xAxis ? app.xAxis.position - app.xAxis.lowerLimit : 0);
	let fovY = $derived(app.yAxis ? app.yAxis.position - app.yAxis.lowerLimit : 0);
	let fovZ = $derived(app.zAxis ? app.zAxis.position - app.zAxis.lowerLimit : 0);
	let thumbnail = $derived(app.previewer?.thumbnailSnapshot ?? '');
	let isXYMoving = $derived(app.xAxis?.isMoving || app.yAxis?.isMoving);
	let isZMoving = $derived(app.zAxis?.isMoving ?? false);
	let hasStage = $derived(app.xAxis && app.yAxis && app.zAxis);
	let stageAspectRatio = $derived(app.stageWidth / app.stageHeight);

	// Local UI state
	let showThumbnail = $state(true);

	// ResizeObserver for responsive sizing
	let containerRef = $state<HTMLDivElement | null>(null);
	let canvasWidth = $state(400);
	let canvasHeight = $state(250);

	// Layout constants (in pixels)
	const TRACK_WIDTH = 12;
	const Z_AREA_WIDTH = TRACK_WIDTH * 2;
	const STAGE_GAP = 16;
	const STAGE_BORDER = 0.5;

	function updateCanvasSize(containerWidth: number, containerHeight: number) {
		// Available space for the SVG (excluding sliders and gap)
		const availableWidth = containerWidth - TRACK_WIDTH - Z_AREA_WIDTH - STAGE_GAP - STAGE_BORDER * 4;
		const availableHeight = containerHeight - TRACK_WIDTH - STAGE_BORDER * 2;

		if (availableWidth <= 0 || availableHeight <= 0) return;

		const containerAspect = availableWidth / availableHeight;

		if (containerAspect > stageAspectRatio) {
			// Height-constrained: use full height, calculate width
			canvasHeight = availableHeight;
			canvasWidth = availableHeight * stageAspectRatio;
		} else {
			// Width-constrained: use full width, calculate height
			canvasWidth = availableWidth;
			canvasHeight = availableWidth / stageAspectRatio;
		}
	}

	onMount(() => {
		if (!containerRef) return;

		const resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const { width, height } = entry.contentRect;
				updateCanvasSize(width, height);
			}
		});

		resizeObserver.observe(containerRef);

		return () => resizeObserver.disconnect();
	});

	// Update canvas size when aspect ratio changes
	$effect(() => {
		if (containerRef) {
			const { width, height } = containerRef.getBoundingClientRect();
			updateCanvasSize(width, height);
		}
	});

	// Convert tile/stack coordinates from μm to mm for SVG rendering
	function toMm(um: number): number {
		return um / 1000;
	}

	// Check if a tile is selected
	function isSelected(tile: Tile): boolean {
		return tile.row === app.selectedTile.row && tile.col === app.selectedTile.col;
	}

	// Handle tile single-click to select
	function handleTileSelect(tile: Tile) {
		app.selectTile(tile.row, tile.col);
	}

	// Clamp position to keep FOV within stage limits
	function clampToStageLimits(targetX: number, targetY: number): [number, number] {
		if (!app.xAxis || !app.yAxis) return [targetX, targetY];
		const minX = app.xAxis.lowerLimit;
		const maxX = app.xAxis.upperLimit - app.fov.width;
		const minY = app.yAxis.lowerLimit;
		const maxY = app.yAxis.upperLimit - app.fov.height;
		return [Math.max(minX, Math.min(maxX, targetX)), Math.max(minY, Math.min(maxY, targetY))];
	}

	// Handle tile double-click to move stage
	function handleTileMove(tile: Tile) {
		if (isXYMoving || !app.xAxis || !app.yAxis) return;
		// Convert tile center position from μm to mm, then clamp to stage limits
		const rawX = app.xAxis.lowerLimit + toMm(tile.x_um) + toMm(tile.w_um) / 2 - app.fov.width / 2;
		const rawY = app.yAxis.lowerLimit + toMm(tile.y_um) + toMm(tile.h_um) / 2 - app.fov.height / 2;
		const [targetX, targetY] = clampToStageLimits(rawX, rawY);
		app.moveXY(targetX, targetY);
	}

	// Handle stack click to select its tile
	function handleStackSelect(stack: Stack) {
		app.selectTile(stack.row, stack.col);
	}

	// Handle stack double-click to move stage
	function handleStackMove(stack: Stack) {
		if (isXYMoving || !app.xAxis || !app.yAxis) return;
		// Move to stack center, clamped to stage limits
		const rawX = app.xAxis.lowerLimit + toMm(stack.x_um) + toMm(stack.w_um) / 2 - app.fov.width / 2;
		const rawY = app.yAxis.lowerLimit + toMm(stack.y_um) + toMm(stack.h_um) / 2 - app.fov.height / 2;
		const [targetX, targetY] = clampToStageLimits(rawX, rawY);
		app.moveXY(targetX, targetY);
	}

	// Handle slider changes
	function handleXSliderChange(e: Event) {
		if (!app.xAxis) return;
		const target = e.target as HTMLInputElement;
		app.xAxis.move(parseFloat(target.value));
	}

	function handleYSliderChange(e: Event) {
		if (!app.yAxis) return;
		const target = e.target as HTMLInputElement;
		app.yAxis.move(parseFloat(target.value));
	}

	function handleZSliderChange(e: Event) {
		if (!app.zAxis) return;
		const target = e.target as HTMLInputElement;
		app.zAxis.move(parseFloat(target.value));
	}

	// Layer visibility toggles
	function toggleGrid() {
		app.layerVisibility = { ...app.layerVisibility, grid: !app.layerVisibility.grid };
	}

	function toggleStacks() {
		app.layerVisibility = { ...app.layerVisibility, stacks: !app.layerVisibility.stacks };
	}

	function togglePath() {
		app.layerVisibility = { ...app.layerVisibility, path: !app.layerVisibility.path };
	}

	function toggleFov() {
		app.layerVisibility = { ...app.layerVisibility, fov: !app.layerVisibility.fov };
	}

	// Keyboard handler for interactive elements
	function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFn();
		}
	}
</script>

{#snippet tileRect(tile: Tile, selected: boolean)}
	{@const x = toMm(tile.x_um)}
	{@const y = toMm(tile.y_um)}
	{@const w = toMm(tile.w_um)}
	{@const h = toMm(tile.h_um)}
	<rect
		{x}
		{y}
		width={w}
		height={h}
		class="tile outline-none"
		class:selected
		class:cursor-pointer={!isXYMoving}
		class:cursor-not-allowed={isXYMoving}
		role="button"
		tabindex={isXYMoving ? -1 : 0}
		onclick={() => handleTileSelect(tile)}
		ondblclick={() => handleTileMove(tile)}
		onkeydown={(e) => handleKeydown(e, () => handleTileSelect(tile))}
	>
		<title>Tile [{tile.row}, {tile.col}]</title>
	</rect>
{/snippet}

<div class="relative grid h-full w-full px-4 pt-18 pb-12">
	{#if hasStage}
		<div class="stage-container flex flex-1 justify-center overflow-hidden" bind:this={containerRef}>
			<!-- Layer visibility floating widget -->
			<div class="absolute top-0 right-4 z-10 flex h-18 items-center">
				<div class="flex gap-0.5 rounded bg-zinc-800/80 p-1 backdrop-blur-sm">
					<button
						onclick={toggleGrid}
						class="rounded p-1 transition-colors {app.layerVisibility.grid
							? 'text-blue-400 hover:bg-zinc-700'
							: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'}"
						title="Toggle grid"
					>
						<Icon icon="mdi:grid" width="14" height="14" />
					</button>
					<button
						onclick={toggleStacks}
						class="rounded p-1 transition-colors {app.layerVisibility.stacks
							? 'text-purple-400 hover:bg-zinc-700'
							: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'}"
						title="Toggle stacks"
					>
						<Icon icon="mdi:layers" width="14" height="14" />
					</button>
					<button
						onclick={togglePath}
						class="rounded p-1 transition-colors {app.layerVisibility.path
							? 'text-fuchsia-400 hover:bg-zinc-700'
							: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'}"
						title="Toggle acquisition path"
					>
						<Icon icon="mdi:vector-polyline" width="14" height="14" />
					</button>
					<button
						onclick={toggleFov}
						class="rounded p-1 transition-colors {app.layerVisibility.fov
							? 'text-emerald-400 hover:bg-zinc-700'
							: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'}"
						title="Toggle FOV"
					>
						<Icon icon="mdi:crosshairs" width="14" height="14" />
					</button>
					<button
						onclick={() => (showThumbnail = !showThumbnail)}
						disabled={!app.layerVisibility.fov}
						class="rounded p-1 transition-colors {showThumbnail && app.layerVisibility.fov
							? 'text-cyan-400 hover:bg-zinc-700'
							: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'} disabled:cursor-not-allowed disabled:opacity-50"
						title="Toggle thumbnail"
					>
						<Icon icon="mdi:image" width="14" height="14" />
					</button>
				</div>
			</div>

			<div
				class="stage-canvas"
				style="--track-width: {TRACK_WIDTH}px; --z-area-width: {Z_AREA_WIDTH}px; --stage-gap: {STAGE_GAP}px; --stage-border-width: {STAGE_BORDER}px;"
			>
				<div class="flex flex-col">
					<div class="flex">
						<div style="width: {TRACK_WIDTH}px"></div>
						<input
							type="range"
							class="x-slider"
							style="width: {canvasWidth}px;"
							min={app.xAxis?.lowerLimit}
							max={app.xAxis?.upperLimit}
							step={0.1}
							value={app.xAxis?.position}
							disabled={isXYMoving}
							oninput={handleXSliderChange}
						/>
					</div>

					<div class="flex min-h-0 items-center">
						<input
							type="range"
							class="y-slider"
							style="height: {canvasHeight}px;"
							min={app.yAxis?.lowerLimit}
							max={app.yAxis?.upperLimit}
							step={0.1}
							value={app.yAxis?.position}
							disabled={isXYMoving}
							oninput={handleYSliderChange}
						/>

						<svg
							viewBox="0 0 {app.stageWidth} {app.stageHeight}"
							class="xy-svg"
							style="width: {canvasWidth}px; height: {canvasHeight}px;"
						>
							<!-- Stacks Layer: Stacks as filled rectangles with status coloring -->
							{#if app.layerVisibility.stacks}
								<g class="stacks-layer">
									{#each app.stacks as stack (`${stack.row}_${stack.col}`)}
										{@const x = toMm(stack.x_um)}
										{@const y = toMm(stack.y_um)}
										{@const w = toMm(stack.w_um)}
										{@const h = toMm(stack.h_um)}
										<rect
											{x}
											{y}
											width={w}
											height={h}
											stroke-width={0.075}
											class="stack outline-none {getStackStatusColor(stack.status)}"
											class:cursor-pointer={!isXYMoving}
											class:cursor-not-allowed={isXYMoving}
											role="button"
											tabindex={isXYMoving ? -1 : 0}
											onclick={() => handleStackSelect(stack)}
											ondblclick={() => handleStackMove(stack)}
											onkeydown={(e) => handleKeydown(e, () => handleStackSelect(stack))}
										>
											<title>Stack [{stack.row}, {stack.col}] - {stack.status} ({stack.num_frames} frames)</title>
										</rect>
									{/each}
								</g>
							{/if}

							<!-- Path Layer: Acquisition order path -->
							{#if app.layerVisibility.path && app.stacks.length > 1}
								{@const pathPoints = app.stacks.map((s) => ({
									x: toMm(s.x_um + s.w_um / 2),
									y: toMm(s.y_um + s.h_um / 2)
								}))}
								<g class="path-layer">
									<!-- Path line -->
									<polyline points={pathPoints.map((p) => `${p.x},${p.y}`).join(' ')} class="acquisition-path" />
									<!-- Arrows at segment midpoints -->
									{#each pathPoints.slice(0, -1) as p1, i (i)}
										{@const p2 = pathPoints[i + 1]}
										{@const midX = (p1.x + p2.x) / 2}
										{@const midY = (p1.y + p2.y) / 2}
										{@const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI)}
										<path
											d="M -0.15 -0.2 L 0.15 0 L -0.15 0.2"
											class="path-arrow-head"
											transform="translate({midX}, {midY}) rotate({angle})"
										/>
									{/each}
								</g>
							{/if}

							<!-- FOV Layer: Current position with thumbnail -->
							{#if app.layerVisibility.fov}
								<g class="fov-layer pointer-events-none">
									<!-- Clip path for thumbnail -->
									<defs>
										<clipPath id="fov-clip">
											<rect x={fovX} y={fovY} width={app.fov.width} height={app.fov.height} />
										</clipPath>
									</defs>

									<!-- Thumbnail image -->
									{#if showThumbnail && thumbnail}
										<image
											href={thumbnail}
											x={fovX}
											y={fovY}
											width={app.fov.width}
											height={app.fov.height}
											clip-path="url(#fov-clip)"
											preserveAspectRatio="xMidYMid slice"
										/>
									{/if}

									<!-- FOV border (outset) -->
									<rect
										x={fovX - 0.025}
										y={fovY - 0.025}
										width={app.fov.width + 0.05}
										height={app.fov.height + 0.05}
										class="fov-rect"
										class:moving={isXYMoving}
									>
										<title>FOV: ({app.xAxis?.position.toFixed(1)}, {app.yAxis?.position.toFixed(1)}) mm</title>
									</rect>
								</g>
							{/if}

							<!-- Grid Layer: Tiles (topmost for easy clicking) -->
							{#if app.layerVisibility.grid}
								{@const selectedTileData = app.tiles.find((t) => isSelected(t))}
								<g class="grid-layer">
									{#each app.tiles as tile (`${tile.row}_${tile.col}`)}
										{#if !isSelected(tile)}
											{@render tileRect(tile, false)}
										{/if}
									{/each}
									{#if selectedTileData}
										{@render tileRect(selectedTileData, true)}
									{/if}
								</g>
							{/if}
						</svg>
					</div>
				</div>

				<div class="z-area" style="height: {canvasHeight + TRACK_WIDTH}px;">
					<input
						type="range"
						class="z-slider"
						min={app.zAxis?.lowerLimit}
						max={app.zAxis?.upperLimit}
						step={0.1}
						value={app.zAxis?.position}
						disabled={isZMoving}
						oninput={handleZSliderChange}
					/>
					<svg viewBox="0 0 30 {app.stageDepth}" class="z-svg" preserveAspectRatio="none">
						<line
							x1="0"
							y1={app.stageDepth - fovZ}
							x2="30"
							y2={app.stageDepth - fovZ}
							class="z-line"
							class:moving={isZMoving}
						>
							<title>Z: {app.zAxis?.position.toFixed(1)} mm</title>
						</line>
					</svg>
				</div>
			</div>
		</div>
	{:else}
		<div class="flex h-64 items-center justify-center rounded border border-zinc-700">
			<p class="text-sm text-zinc-500">Stage not available</p>
		</div>
	{/if}
</div>

<style>
	.stage-canvas {
		--thumb-width: 2px;
		--stage-border: var(--stage-border-width) solid var(--color-zinc-600);
		display: flex;
		gap: var(--stage-gap);
	}

	.stage-canvas input[type='range'] {
		-webkit-appearance: none;
		appearance: none;
		cursor: pointer;
		margin: 0;
		padding: 0;
		background-color: var(--color-zinc-900);
		border: var(--stage-border);

		&::-webkit-slider-runnable-track {
			background: transparent;
			border-radius: 0;
		}
		&::-moz-range-track {
			background: transparent;
			border-radius: 0;
		}

		&::-webkit-slider-thumb {
			-webkit-appearance: none;
			appearance: none;
			background: var(--color-emerald-500);
			border-radius: 1px;
			cursor: pointer;
		}

		&::-moz-range-thumb {
			appearance: none;
			background: var(--color-emerald-500);
			border: none;
			border-radius: 1px;
			cursor: pointer;
		}

		&:disabled {
			cursor: not-allowed;
			&::-webkit-slider-thumb {
				background: var(--color-rose-500);
			}
			&::-moz-range-thumb {
				background: var(--color-rose-500);
			}
		}
	}

	.x-slider {
		height: var(--track-width);
		&::-webkit-slider-thumb {
			width: var(--thumb-width);
			height: var(--track-width);
		}
		&::-moz-range-thumb {
			width: var(--thumb-width);
			height: var(--track-width);
		}
	}

	.y-slider {
		writing-mode: vertical-rl;
		direction: ltr;
		width: var(--track-width);
		&::-webkit-slider-thumb {
			width: var(--track-width);
			height: var(--thumb-width);
		}
		&::-moz-range-thumb {
			width: var(--track-width);
			height: var(--thumb-width);
		}
	}

	.z-area {
		width: var(--z-area-width);
		position: relative;
		flex: 1;
	}

	.z-slider {
		position: absolute;
		inset: 0;
		writing-mode: vertical-rl;
		direction: rtl;
		width: 100%;
		height: 100%;
		z-index: 1;
		&::-webkit-slider-thumb {
			width: var(--z-area-width);
			height: var(--thumb-width);
		}
		&::-moz-range-thumb {
			width: var(--z-area-width);
			height: var(--thumb-width);
		}
	}

	.xy-svg {
		flex-shrink: 0;
		border-right: var(--stage-border);
		border-bottom: var(--stage-border);
	}

	.z-svg {
		position: absolute;
		inset: 0;
		pointer-events: none;
		z-index: 2;
	}

	.z-line {
		stroke: var(--color-emerald-500);
		stroke-width: 0.2;
		&.moving {
			stroke: var(--color-rose-500);
		}
	}

	.tile {
		fill: transparent;
		stroke: var(--color-zinc-700);
		stroke-width: 0.05;
		transition:
			fill 150ms ease,
			stroke 150ms ease;
		&:hover {
			fill: color-mix(in srgb, var(--color-zinc-500) 15%, transparent);
		}
		&.selected {
			stroke: var(--color-amber-500);
			stroke-width: 0.05;
		}
	}

	.fov-rect {
		fill: none;
		stroke: var(--color-emerald-400);
		stroke-width: 0.1;
		&.moving {
			stroke: var(--color-rose-400);
		}
	}

	.path-layer {
		pointer-events: none;
	}

	.acquisition-path {
		fill: none;
		stroke: var(--color-fuchsia-500);
		stroke-width: 0.04;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.path-arrow-head {
		fill: none;
		stroke: var(--color-fuchsia-500);
		stroke-width: 0.06;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.stack {
		fill: currentColor;
		fill-opacity: 0.15;
		stroke: currentColor;
		transition: fill-opacity 150ms ease;
		&:hover {
			fill-opacity: 0.35;
		}
	}
</style>
