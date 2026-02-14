<script lang="ts">
	import type { App } from '$lib/app';
	import { getStackStatusColor, type Tile, type Stack } from '$lib/core/types';
	import { onMount } from 'svelte';
	import { compositeFullFrames } from '$lib/app/preview.svelte.ts';
	import GridControls from './GridControls.svelte';
	import StageControls from './StageControls.svelte';
	import LayerToggles from './LayerToggles.svelte';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	let fovX = $derived(app.xAxis ? app.xAxis.position - app.xAxis.lowerLimit : 0);
	let fovY = $derived(app.yAxis ? app.yAxis.position - app.yAxis.lowerLimit : 0);
	let fovZ = $derived(app.zAxis ? app.zAxis.position - app.zAxis.lowerLimit : 0);
	let isXYMoving = $derived(app.xAxis?.isMoving || app.yAxis?.isMoving);
	let isZMoving = $derived(app.zAxis?.isMoving ?? false);

	let primaryTile = $derived(app.selectedTiles[0] ?? null);
	let primaryStack = $derived(
		primaryTile ? (app.stacks.find((s) => s.row === primaryTile.row && s.col === primaryTile.col) ?? null) : null
	);

	let marginX = $derived(app.fov.width / 2);
	let marginY = $derived(app.fov.height / 2);

	let viewBoxWidth = $derived(app.stageWidth + app.fov.width);
	let viewBoxHeight = $derived(app.stageHeight + app.fov.height);
	let stageAspectRatio = $derived(viewBoxWidth / viewBoxHeight);
	let cornerLen = $derived(Math.min(app.fov.width, app.fov.height) / 8);

	let showThumbnail = $state(true);

	const FOV_RESOLUTION = 256;
	let thumbnail = $state('');
	let fovNeedsRedraw = false;
	let fovAnimFrameId: number | null = null;

	const offscreen = document.createElement('canvas');
	offscreen.width = FOV_RESOLUTION;
	const offscreenCtx = offscreen.getContext('2d')!;

	$effect(() => {
		const aspect = app.fov.width / app.fov.height;
		if (aspect > 0 && Number.isFinite(aspect)) {
			offscreen.height = Math.round(FOV_RESOLUTION / aspect);
		}
	});

	$effect(() => {
		if (app.previewState) {
			void app.previewState.redrawGeneration;
			fovNeedsRedraw = true;
		}
	});

	function fovFrameLoop() {
		if (fovNeedsRedraw && app.previewState) {
			fovNeedsRedraw = false;
			compositeFullFrames(offscreenCtx, offscreen, app.previewState.channels);
			thumbnail = offscreen.toDataURL('image/jpeg', 0.6);
		}
		fovAnimFrameId = requestAnimationFrame(fovFrameLoop);
	}

	let containerRef = $state<HTMLDivElement | null>(null);
	let canvasWidth = $state(400);
	let canvasHeight = $state(250);

	const TRACK_WIDTH = 16;
	const Z_AREA_WIDTH = TRACK_WIDTH;
	const STAGE_GAP = 16;
	const STAGE_BORDER = 0.5;

	let scale = $derived(canvasWidth / viewBoxWidth);
	let marginPixelsX = $derived(marginX * scale);
	let marginPixelsY = $derived(marginY * scale);
	let stagePixelsX = $derived(app.stageWidth * scale);
	let stagePixelsY = $derived(app.stageHeight * scale);

	function updateCanvasSize(containerWidth: number, containerHeight: number) {
		const availableWidth = containerWidth - TRACK_WIDTH - Z_AREA_WIDTH - STAGE_GAP - STAGE_BORDER * 4;
		const availableHeight = containerHeight - TRACK_WIDTH - STAGE_BORDER * 2;

		if (availableWidth <= 0 || availableHeight <= 0) return;

		const containerAspect = availableWidth / availableHeight;

		if (containerAspect > stageAspectRatio) {
			canvasHeight = availableHeight;
			canvasWidth = availableHeight * stageAspectRatio;
		} else {
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

		fovFrameLoop();

		return () => {
			resizeObserver.disconnect();
			if (fovAnimFrameId !== null) cancelAnimationFrame(fovAnimFrameId);
		};
	});

	$effect(() => {
		if (containerRef) {
			const { width, height } = containerRef.getBoundingClientRect();
			updateCanvasSize(width, height);
		}
	});

	function toMm(um: number): number {
		return um / 1000;
	}

	function isSelected(tile: Tile): boolean {
		return app.isTileSelected(tile.row, tile.col);
	}

	function handleTileSelect(e: MouseEvent, tile: Tile) {
		if (e.ctrlKey || e.metaKey) {
			if (app.isTileSelected(tile.row, tile.col)) app.removeFromSelection([[tile.row, tile.col]]);
			else app.addToSelection([[tile.row, tile.col]]);
		} else {
			app.selectTiles([[tile.row, tile.col]]);
		}
	}

	function clampToStageLimits(targetX: number, targetY: number): [number, number] {
		if (!app.xAxis || !app.yAxis) return [targetX, targetY];
		const minX = app.xAxis.lowerLimit;
		const maxX = app.xAxis.upperLimit;
		const minY = app.yAxis.lowerLimit;
		const maxY = app.yAxis.upperLimit;
		return [Math.max(minX, Math.min(maxX, targetX)), Math.max(minY, Math.min(maxY, targetY))];
	}

	function handleTileMove(e: MouseEvent, tile: Tile) {
		if (e.button !== 1) return;
		e.preventDefault();
		if (isXYMoving || !app.xAxis || !app.yAxis) return;
		const targetX = app.xAxis.lowerLimit + toMm(tile.x_um);
		const targetY = app.yAxis.lowerLimit + toMm(tile.y_um);
		const [clampedX, clampedY] = clampToStageLimits(targetX, targetY);
		app.moveXY(clampedX, clampedY);
	}

	function handleStackSelect(e: MouseEvent, stack: Stack) {
		if (e.ctrlKey || e.metaKey) {
			if (app.isTileSelected(stack.row, stack.col)) app.removeFromSelection([[stack.row, stack.col]]);
			else app.addToSelection([[stack.row, stack.col]]);
		} else {
			app.selectTiles([[stack.row, stack.col]]);
		}
	}

	function handleStackMove(e: MouseEvent, stack: Stack) {
		if (e.button !== 1) return;
		e.preventDefault();
		if (isXYMoving || !app.xAxis || !app.yAxis) return;
		const targetX = app.xAxis.lowerLimit + toMm(stack.x_um);
		const targetY = app.yAxis.lowerLimit + toMm(stack.y_um);
		const [clampedX, clampedY] = clampToStageLimits(targetX, targetY);
		app.moveXY(clampedX, clampedY);
	}

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

	function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFn();
		}
	}
</script>

{#snippet tileRect(tile: Tile, selected: boolean)}
	{@const cx = toMm(tile.x_um)}
	{@const cy = toMm(tile.y_um)}
	{@const w = toMm(tile.w_um)}
	{@const h = toMm(tile.h_um)}
	{@const x = cx - w / 2}
	{@const y = cy - h / 2}
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
		onclick={(e) => handleTileSelect(e, tile)}
		onauxclick={(e) => handleTileMove(e, tile)}
		onkeydown={(e) => handleKeydown(e, () => app.selectTiles([[tile.row, tile.col]]))}
	>
		<title>Tile [{tile.row}, {tile.col}]</title>
	</rect>
{/snippet}

<div class="flex h-full w-full flex-col p-2">
	{#if app.xAxis && app.yAxis && app.zAxis}
		<div class="py-4">
			<StageControls xAxis={app.xAxis} yAxis={app.yAxis} zAxis={app.zAxis} />
		</div>

		<div class="stage-container relative flex min-h-0 flex-1 justify-center overflow-hidden" bind:this={containerRef}>
			<div
				class="stage-canvas"
				style:--track-width="{TRACK_WIDTH}px"
				style:--z-area-width="{Z_AREA_WIDTH}px"
				style:--stage-gap="{STAGE_GAP}px"
				style:--stage-border-width="{STAGE_BORDER}px"
			>
				<div class="flex flex-col">
					<input
						type="range"
						class="x-slider"
						style="width: {stagePixelsX}px; margin-left: {TRACK_WIDTH + STAGE_BORDER + marginPixelsX}px;"
						min={app.xAxis?.lowerLimit}
						max={app.xAxis?.upperLimit}
						step={0.1}
						value={app.xAxis?.position}
						disabled={isXYMoving}
						oninput={handleXSliderChange}
					/>

					<div class="flex min-h-0 items-start">
						<input
							type="range"
							class="y-slider"
							style="height: {stagePixelsY}px; margin-top: {STAGE_BORDER + marginPixelsY}px;"
							min={app.yAxis?.lowerLimit}
							max={app.yAxis?.upperLimit}
							step={0.1}
							value={app.yAxis?.position}
							disabled={isXYMoving}
							oninput={handleYSliderChange}
						/>

						<svg
							viewBox="{-marginX} {-marginY} {viewBoxWidth} {viewBoxHeight}"
							class="xy-svg"
							style="width: {canvasWidth}px; height: {canvasHeight}px;"
						>
							{#if app.layerVisibility.stacks}
								<g class="stacks-layer">
									{#each app.stacks as stack (`${stack.row}_${stack.col}`)}
										{@const cx = toMm(stack.x_um)}
										{@const cy = toMm(stack.y_um)}
										{@const w = toMm(stack.w_um)}
										{@const h = toMm(stack.h_um)}
										{@const x = cx - w / 2}
										{@const y = cy - h / 2}
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
											onclick={(e) => handleStackSelect(e, stack)}
											onauxclick={(e) => handleStackMove(e, stack)}
											onkeydown={(e) => handleKeydown(e, () => app.selectTiles([[stack.row, stack.col]]))}
										>
											<title>Stack [{stack.row}, {stack.col}] - {stack.status} ({stack.num_frames} frames)</title>
										</rect>
									{/each}
								</g>
							{/if}

							{#if app.layerVisibility.path && app.stacks.length > 1}
								{@const pathPoints = app.stacks.map((s) => ({
									x: toMm(s.x_um),
									y: toMm(s.y_um)
								}))}
								<g class="path-layer">
									<polyline points={pathPoints.map((p) => `${p.x},${p.y}`).join(' ')} class="acquisition-path" />
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

							{#if app.layerVisibility.fov}
								{@const fovLeft = fovX - app.fov.width / 2}
								{@const fovTop = fovY - app.fov.height / 2}
								<g class="fov-layer pointer-events-none">
									<defs>
										<clipPath id="fov-clip">
											<rect x={fovLeft} y={fovTop} width={app.fov.width} height={app.fov.height} />
										</clipPath>
									</defs>

									{#if showThumbnail && thumbnail}
										<image
											href={thumbnail}
											x={fovLeft}
											y={fovTop}
											width={app.fov.width}
											height={app.fov.height}
											clip-path="url(#fov-clip)"
											preserveAspectRatio="xMidYMid slice"
										/>
									{/if}

									<rect
										x={fovLeft - 0.025}
										y={fovTop - 0.025}
										width={app.fov.width + 0.05}
										height={app.fov.height + 0.05}
										class="fov-rect"
										class:moving={isXYMoving}
									>
										<title>FOV: ({app.xAxis?.position.toFixed(1)}, {app.yAxis?.position.toFixed(1)}) mm</title>
									</rect>

									<g class="fov-crosshair" class:moving={isXYMoving}>
										<line x1={fovX - 0.3} y1={fovY} x2={fovX + 0.3} y2={fovY} />
										<line x1={fovX} y1={fovY - 0.3} x2={fovX} y2={fovY + 0.3} />
									</g>
								</g>
							{/if}

							{#if app.layerVisibility.grid}
								<g class="grid-layer">
									{#each app.tiles as tile (`${tile.row}_${tile.col}`)}
										{#if !isSelected(tile)}
											{@render tileRect(tile, false)}
										{/if}
									{/each}
									{#each app.tiles as tile (`s_${tile.row}_${tile.col}`)}
										{#if isSelected(tile)}
											{@render tileRect(tile, true)}
										{/if}
									{/each}
								</g>
							{/if}

							<g class="corner-marks">
								<polyline
									points="{-marginX + cornerLen},{-marginY} {-marginX},{-marginY} {-marginX},{-marginY + cornerLen}"
								/>
								<polyline
									points="{-marginX + viewBoxWidth - cornerLen},{-marginY} {-marginX +
										viewBoxWidth},{-marginY} {-marginX + viewBoxWidth},{-marginY + cornerLen}"
								/>
								<polyline
									points="{-marginX},{-marginY + viewBoxHeight - cornerLen} {-marginX},{-marginY +
										viewBoxHeight} {-marginX + cornerLen},{-marginY + viewBoxHeight}"
								/>
								<polyline
									points="{-marginX + viewBoxWidth - cornerLen},{-marginY + viewBoxHeight} {-marginX +
										viewBoxWidth},{-marginY + viewBoxHeight} {-marginX + viewBoxWidth},{-marginY +
										viewBoxHeight -
										cornerLen}"
								/>
							</g>
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
					<svg viewBox="0 0 30 {canvasHeight}" class="z-svg" preserveAspectRatio="none" width="100%" height="100%">
						{#if primaryStack && app.zAxis}
							{@const z0Offset = primaryStack.z_start_um / 1000 - app.zAxis.lowerLimit}
							{@const z1Offset = primaryStack.z_end_um / 1000 - app.zAxis.lowerLimit}
							{@const y0 = (1 - z0Offset / app.stageDepth) * canvasHeight - 1}
							{@const y1 = (1 - z1Offset / app.stageDepth) * canvasHeight - 1}
							<g class={getStackStatusColor(primaryStack.status)}>
								<line x1="0" y1={y0} x2="30" y2={y0} class="z-marker" />
								<line x1="0" {y1} x2="30" y2={y1} class="z-marker" />
							</g>
						{/if}
						<line
							x1="0"
							y1={(1 - fovZ / app.stageDepth) * canvasHeight - 1}
							x2="30"
							y2={(1 - fovZ / app.stageDepth) * canvasHeight - 1}
							class="z-line"
							class:moving={isZMoving}
						>
							<title>Z: {app.zAxis?.position.toFixed(1)} mm</title>
						</line>
					</svg>
				</div>
			</div>
		</div>

		<div class="flex items-center justify-between py-4">
			<GridControls {app} />
			<LayerToggles {app} bind:showThumbnail />
		</div>
	{:else}
		<div class="flex h-64 items-center justify-center rounded border border-border">
			<p class="text-sm text-muted-foreground">Stage not available</p>
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
		border-bottom: none;
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
		border-right: none;
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
		background-color: var(--color-zinc-900);
		border: var(--stage-border);
	}

	.z-slider {
		position: absolute;
		inset: 0;
		writing-mode: vertical-rl;
		direction: rtl;
		width: 100%;
		height: 100%;
		z-index: 1;
		background: transparent;
		border: none;
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
	}

	.corner-marks {
		pointer-events: none;
		& polyline {
			fill: none;
			stroke: var(--color-zinc-600);
			stroke-width: 0.08;
			stroke-linecap: square;
		}
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

	.z-marker {
		stroke: currentColor;
		stroke-width: 2;
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

	.fov-crosshair {
		stroke: var(--color-emerald-400);
		stroke-width: 0.05;
		opacity: 0.7;
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
