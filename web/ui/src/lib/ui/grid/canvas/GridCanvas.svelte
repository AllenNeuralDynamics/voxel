<script lang="ts">
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type Tile, type Stack } from '$lib/main/types';
	import { onMount } from 'svelte';
	import { compositeFullFrames } from '$lib/main/preview.svelte.ts';
	import StageSlider from './StageSlider.svelte';
	import StagePosition from './StagePosition.svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	// ── Geometry ─────────────────────────────────────────────────────────

	const SLIDER_WIDTH = 16;
	const Z_AREA_WIDTH = SLIDER_WIDTH * 2;
	const STAGE_GAP = 16;
	const STAGE_BORDER = 0.5;
	const TOGGLES_HEIGHT = 30;

	const ARROW_HEAD = 'M -0.15 -0.2 L 0.15 0 L -0.15 0.2';
	const Z_SVG_WIDTH = 30;

	let isXYMoving = $derived(session.xAxis?.isMoving || session.yAxis?.isMoving);
	let isZMoving = $derived(session.zAxis?.isMoving ?? false);

	// FOV position relative to stage origin (lower limits)
	let fovX = $derived(session.xAxis ? session.xAxis.position - session.xAxis.lowerLimit : 0);
	let fovY = $derived(session.yAxis ? session.yAxis.position - session.yAxis.lowerLimit : 0);
	let fovZ = $derived(session.zAxis ? session.zAxis.position - session.zAxis.lowerLimit : 0);
	let fovLeft = $derived(fovX - session.fov.width / 2);
	let fovTop = $derived(fovY - session.fov.height / 2);

	// ViewBox: stage bounds + one FOV of margin on each side
	let marginX = $derived(session.fov.width / 2);
	let marginY = $derived(session.fov.height / 2);
	let viewBoxWidth = $derived(session.stageWidth + session.fov.width);
	let viewBoxHeight = $derived(session.stageHeight + session.fov.height);
	let viewBoxStr = $derived(`${-marginX} ${-marginY} ${viewBoxWidth} ${viewBoxHeight}`);

	// ── Canvas sizing ────────────────────────────────────────────────────

	let containerRef = $state<HTMLDivElement | null>(null);
	let canvasWidth = $state(400);
	let canvasHeight = $state(250);

	let stageAspectRatio = $derived(viewBoxWidth / viewBoxHeight);
	let scale = $derived(canvasWidth / viewBoxWidth);
	let marginPixelsX = $derived(marginX * scale);
	let marginPixelsY = $derived(marginY * scale);
	let stagePixelsX = $derived(session.stageWidth * scale);
	let stagePixelsY = $derived(session.stageHeight * scale);
	let thumbThickness = 1;

	let zLineY = $derived((1 - fovZ / session.stageDepth) * canvasHeight - 1);

	function updateCanvasSize(containerWidth: number, containerHeight: number) {
		const availableWidth = containerWidth - SLIDER_WIDTH / 2 - Z_AREA_WIDTH - STAGE_GAP - STAGE_BORDER * 2;
		const availableHeight = containerHeight - SLIDER_WIDTH / 2 - TOGGLES_HEIGHT;
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

	// ── FOV thumbnail ────────────────────────────────────────────────────

	let showThumbnail = $state(true);

	const FOV_RESOLUTION = 256;
	let thumbnail = $state('');
	let fovNeedsRedraw = false;
	let fovAnimFrameId: number | null = null;

	const offscreen = document.createElement('canvas');
	offscreen.width = FOV_RESOLUTION;
	const offscreenCtx = offscreen.getContext('2d')!;

	$effect(() => {
		const aspect = session.fov.width / session.fov.height;
		if (aspect > 0 && Number.isFinite(aspect)) {
			offscreen.height = Math.round(FOV_RESOLUTION / aspect);
		}
	});

	$effect(() => {
		if (session.previewState) {
			void session.previewState.redrawGeneration;
			fovNeedsRedraw = true;
		}
	});

	function fovFrameLoop() {
		if (fovNeedsRedraw && session.previewState) {
			fovNeedsRedraw = false;
			compositeFullFrames(offscreenCtx, offscreen, session.previewState.channels);
			thumbnail = offscreen.toDataURL('image/jpeg', 0.6);
		}
		fovAnimFrameId = requestAnimationFrame(fovFrameLoop);
	}

	// ── Interaction handlers ─────────────────────────────────────────────

	function toMm(um: number): number {
		return um / 1000;
	}

	function isSelected(tile: Tile): boolean {
		return session.isTileSelected(tile.row, tile.col);
	}

	function clampToStageLimits(targetX: number, targetY: number): [number, number] {
		if (!session.xAxis || !session.yAxis) return [targetX, targetY];
		return [
			Math.max(session.xAxis.lowerLimit, Math.min(session.xAxis.upperLimit, targetX)),
			Math.max(session.yAxis.lowerLimit, Math.min(session.yAxis.upperLimit, targetY))
		];
	}

	function moveToTilePosition(x_um: number, y_um: number) {
		if (isXYMoving || !session.xAxis || !session.yAxis) return;
		const targetX = session.xAxis.lowerLimit + toMm(x_um);
		const targetY = session.yAxis.lowerLimit + toMm(y_um);
		const [clampedX, clampedY] = clampToStageLimits(targetX, targetY);
		session.moveXY(clampedX, clampedY);
	}

	function handleTileSelect(e: MouseEvent, tile: Tile) {
		if (e.ctrlKey || e.metaKey) {
			if (session.isTileSelected(tile.row, tile.col)) session.removeFromSelection([[tile.row, tile.col]]);
			else session.addToSelection([[tile.row, tile.col]]);
		} else {
			session.selectTiles([[tile.row, tile.col]]);
		}
	}

	function handleTileMove(e: MouseEvent, tile: Tile) {
		if (e.button !== 1) return;
		e.preventDefault();
		moveToTilePosition(tile.x_um, tile.y_um);
	}

	function handleStackSelect(e: MouseEvent, stack: Stack) {
		if (e.ctrlKey || e.metaKey) {
			if (session.isTileSelected(stack.row, stack.col)) session.removeFromSelection([[stack.row, stack.col]]);
			else session.addToSelection([[stack.row, stack.col]]);
		} else {
			session.selectTiles([[stack.row, stack.col]]);
		}
	}

	function handleStackMove(e: MouseEvent, stack: Stack) {
		if (e.button !== 1) return;
		e.preventDefault();
		moveToTilePosition(stack.x_um, stack.y_um);
	}

	function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFn();
		}
	}

	function toggleLayer(key: keyof typeof session.layerVisibility) {
		session.layerVisibility = { ...session.layerVisibility, [key]: !session.layerVisibility[key] };
	}

	type Layer = {
		key: keyof typeof session.layerVisibility;
		color: string;
		icon: string;
		title: string;
	};
</script>

{#snippet layerToggle(
	active: boolean,
	activeColor: string,
	icon: string,
	title: string,
	onclick: () => void,
	disabled?: boolean
)}
	<button
		{onclick}
		{disabled}
		class="rounded p-1 transition-colors {active
			? `${activeColor} hover:bg-zinc-700`
			: 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300'} disabled:cursor-not-allowed disabled:opacity-50"
		{title}
	>
		<Icon {icon} width="14" height="14" />
	</button>
{/snippet}

<!-- ── SVG layer snippets ─────────────────────────────────────────────── -->

{#snippet stacksLayer()}
	{#if session.layerVisibility.stacks}
		<g class="stacks-layer">
			{#each session.stacks as stack (`${stack.row}_${stack.col}`)}
				{@const cx = toMm(stack.x_um)}
				{@const cy = toMm(stack.y_um)}
				{@const w = toMm(stack.w_um)}
				{@const h = toMm(stack.h_um)}
				<rect
					x={cx - w / 2}
					y={cy - h / 2}
					width={w}
					height={h}
					class="nss stack outline-none {getStackStatusColor(stack.status)}"
					class:cursor-pointer={!isXYMoving}
					class:cursor-not-allowed={isXYMoving}
					role="button"
					tabindex={isXYMoving ? -1 : 0}
					onclick={(e) => handleStackSelect(e, stack)}
					onauxclick={(e) => handleStackMove(e, stack)}
					onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[stack.row, stack.col]]))}
				>
					<title>Stack [{stack.row}, {stack.col}] - {stack.status} ({stack.num_frames} frames)</title>
				</rect>
			{/each}
		</g>
	{/if}
{/snippet}

{#snippet pathLayer()}
	{#if session.layerVisibility.path && session.stacks.length > 1}
		{@const points = session.stacks.map((s) => ({ x: toMm(s.x_um), y: toMm(s.y_um) }))}
		<g class="pointer-none text-slate-400" stroke="currentColor" stroke-linecap="square">
			<polyline
				class="nss fill-none opacity-35"
				stroke-width="1.5"
				points={points.map((p) => `${p.x},${p.y}`).join(' ')}
			/>
			{#each points.slice(0, -1) as p1, i (i)}
				{@const p2 = points[i + 1]}
				{@const midX = (p1.x + p2.x) / 2}
				{@const midY = (p1.y + p2.y) / 2}
				{@const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI)}
				<path
					d={ARROW_HEAD}
					stroke-width="1"
					class="nss opacity-70"
					transform="translate({midX}, {midY}) rotate({angle})"
				/>
			{/each}
		</g>
	{/if}
{/snippet}

{#snippet fovLayer()}
	{#if session.layerVisibility.fov}
		<g class="fov-layer pointer-events-none">
			<defs>
				<clipPath id="fov-clip">
					<rect x={fovLeft} y={fovTop} width={session.fov.width} height={session.fov.height} />
				</clipPath>
			</defs>

			{#if showThumbnail && thumbnail}
				<image
					href={thumbnail}
					x={fovLeft}
					y={fovTop}
					width={session.fov.width}
					height={session.fov.height}
					clip-path="url(#fov-clip)"
					preserveAspectRatio="xMidYMid slice"
				/>
			{/if}

			<g>
				<line
					class="nss"
					x1={-marginX}
					y1={fovY}
					x2={-marginX + viewBoxWidth}
					y2={fovY}
					stroke-width="1"
					stroke={session.yAxis?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
				/>
				<line
					class="nss"
					x1={fovX}
					y1={-marginY}
					x2={fovX}
					y2={-marginY + viewBoxHeight}
					stroke-width="1"
					stroke={session.xAxis?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
				/>
			</g>
		</g>
	{/if}
{/snippet}

{#snippet tileRect(tile: Tile, selected: boolean)}
	{@const cx = toMm(tile.x_um)}
	{@const cy = toMm(tile.y_um)}
	{@const w = toMm(tile.w_um)}
	{@const h = toMm(tile.h_um)}
	<rect
		x={cx - w / 2}
		y={cy - h / 2}
		width={w}
		height={h}
		class="nss tile outline-none"
		class:selected
		class:cursor-pointer={!isXYMoving}
		class:cursor-not-allowed={isXYMoving}
		role="button"
		tabindex={isXYMoving ? -1 : 0}
		onclick={(e) => handleTileSelect(e, tile)}
		onauxclick={(e) => handleTileMove(e, tile)}
		onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[tile.row, tile.col]]))}
	>
		<title>Tile [{tile.row}, {tile.col}]</title>
	</rect>
{/snippet}

{#snippet gridLayer()}
	{#if session.layerVisibility.grid}
		<g class="grid-layer">
			{#each session.tiles as tile (`${tile.row}_${tile.col}`)}
				{#if !isSelected(tile)}
					{@render tileRect(tile, false)}
				{/if}
			{/each}
			{#each session.tiles as tile (`s_${tile.row}_${tile.col}`)}
				{#if isSelected(tile)}
					{@render tileRect(tile, true)}
				{/if}
			{/each}
		</g>
	{/if}
{/snippet}

<!-- ── Layout ─────────────────────────────────────────────────────────── -->

<div class="flex h-full w-full flex-col p-2">
	{#if session.xAxis && session.yAxis && session.zAxis}
		{@const layers: Layer[] = [
			{ key: 'grid', color: 'text-blue-500', icon: 'lucide-lab:grid-lines', title: 'Toggle grid' },
			{ key: 'stacks', color: 'text-blue-400', icon: 'ph:stack-light', title: 'Toggle stacks' },
			{ key: 'path', color: 'text-slate-400', icon: 'iconoir:path-arrow', title: 'Toggle path' },
			{ key: 'fov', color: 'text-success', icon: 'mdi:plus', title: 'Toggle FOV' },
		]}

		<div class="grid flex-1 grid-rows-[1fr_auto] overflow-hidden" bind:this={containerRef}>
			<div class="flex place-self-center" style:gap="{STAGE_GAP}px" style:--thumb-width="{thumbThickness}px">
					<div
						class="grid"
						style="grid-template-columns: {SLIDER_WIDTH / 2}px auto; grid-template-rows: {SLIDER_WIDTH / 2}px 1fr;"
						style:--slider-width="{SLIDER_WIDTH}px"
					>
						<StageSlider
							orientation="horizontal"
							style="grid-column: 2; width: {stagePixelsX}px; height: {SLIDER_WIDTH}px; margin-left: {marginPixelsX +
								0.5}px; transform: translateY(0.5px);"
							min={session.xAxis.lowerLimit}
							max={session.xAxis.upperLimit}
							step={0.1}
							position={session.xAxis.position}
							isMoving={session.xAxis.isMoving}
							onmove={(v) => session.xAxis?.move(v)}
						/>

						<StageSlider
							orientation="vertical-ltr"
							style="grid-column: 1; grid-row: 2; width: {SLIDER_WIDTH}px; height: {stagePixelsY}px; margin-top: {marginPixelsY}px; transform: translateX(0.5px);"
							min={session.yAxis.lowerLimit}
							max={session.yAxis.upperLimit}
							step={0.1}
							position={session.yAxis.position}
							isMoving={session.yAxis.isMoving}
							onmove={(v) => session.yAxis?.move(v)}
						/>

						<svg
							viewBox={viewBoxStr}
							class="border border-zinc-700"
							style="grid-column: 2; grid-row: 2; width: {canvasWidth}px; height: {canvasHeight}px;"
							overflow="hidden"
						>
							{@render fovLayer()}
							{@render gridLayer()}
							{@render stacksLayer()}
							{@render pathLayer()}
						</svg>
					</div>

					<div
						class="relative border border-zinc-600 transition-colors duration-300 ease-in-out hover:bg-zinc-900"
						style="height: {canvasHeight}px; margin-top: {SLIDER_WIDTH / 2}px; width: {Z_AREA_WIDTH}px"
					>
						<StageSlider
							orientation="vertical-rtl"
							style="position: absolute; inset: 0; z-index: 10; width: 100%; height: 100%; --slider-width: {Z_AREA_WIDTH}px;"
							min={session.zAxis.lowerLimit}
							max={session.zAxis.upperLimit}
							step={0.1}
							position={session.zAxis.position}
							isMoving={isZMoving}
							onmove={(v) => session.zAxis?.move(v)}
						/>
						<svg
							viewBox="0 0 {Z_SVG_WIDTH} {canvasHeight}"
							class="z-svg pointer-none absolute inset-0 z-0"
							preserveAspectRatio="none"
							width="100%"
							height="100%"
						>
							{#if session.zAxis}
								{#each session.stacks as stack (`z_${stack.row}_${stack.col}`)}
									{@const selected = session.isTileSelected(stack.row, stack.col)}
									{@const z0Y =
										(1 - (stack.z_start_um / 1000 - session.zAxis.lowerLimit) / session.stageDepth) * canvasHeight - 1}
									{@const z1Y =
										(1 - (stack.z_end_um / 1000 - session.zAxis.lowerLimit) / session.stageDepth) * canvasHeight - 1}
									<g
										class={getStackStatusColor(stack.status)}
										stroke-width={selected ? '1.5' : '0.5'}
										stroke="currentColor"
										opacity={selected ? 1 : 0.3}
									>
										<line class="nss" x1="0" y1={z0Y} x2={Z_SVG_WIDTH} y2={z0Y} />
										<line class="nss" x1="0" y1={z1Y} x2={Z_SVG_WIDTH} y2={z1Y} />
									</g>
								{/each}
							{/if}
							<line
								x1="0"
								y1={zLineY}
								x2={Z_SVG_WIDTH}
								y2={zLineY}
								class="nss z-line"
								class:moving={isZMoving}
								stroke-width="1"
								stroke={session.zAxis?.isMoving ? 'var(--color-danger)' : 'var(--color-success'}
							>
								<title>Z: {session.zAxis?.position.toFixed(1)} mm</title>
							</line>
						</svg>
					</div>
			</div>

			<div class="flex w-full items-center justify-between">
				<div class="flex gap-0.5">
					{#each layers as { key, color, icon, title } (key)}
						{@render layerToggle(session.layerVisibility[key], color, icon, title, () => toggleLayer(key))}
					{/each}
					{@render layerToggle(
						showThumbnail && session.layerVisibility.fov,
						'text-success',
						'ph:image-light',
						'Toggle thumbnail',
						() => (showThumbnail = !showThumbnail),
						!session.layerVisibility.fov
					)}
				</div>
				<StagePosition {session} />
			</div>
		</div>
	{:else}
		<div class="grid flex-1 place-content-center">
			<p class="text-sm text-muted-foreground">Stage not available</p>
		</div>
	{/if}
</div>

<!-- ── Styles ─────────────────────────────────────────────────────────── -->

<style>
	/* SVG elements */

	.nss {
		vector-effect: non-scaling-stroke;
	}

	.tile {
		fill: transparent;
		stroke: var(--color-zinc-700);
		stroke-width: 1;
		transition:
			fill 300ms ease,
			stroke 150ms ease;
		&:hover {
			fill: color-mix(in srgb, var(--color-zinc-500) 25%, transparent);
		}
		&.selected {
			stroke: var(--color-amber-400);
		}
	}

	.stack {
		fill: currentColor;
		fill-opacity: 0.2;
		transition: fill-opacity 300ms ease;
		&:hover {
			fill-opacity: 0.3;
		}
	}
</style>
