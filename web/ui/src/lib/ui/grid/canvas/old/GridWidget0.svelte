<script lang="ts">
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type Tile, type Stack } from '$lib/main/types';
	import { onMount } from 'svelte';
	import { compositeFullFrames } from '$lib/main/preview.svelte.ts';
	import { Button, SpinBox } from '$lib/ui/primitives';
	import Icon from '@iconify/svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let fovX = $derived(session.stage.x ? session.stage.x.position - session.stage.x.lowerLimit : 0);
	let fovY = $derived(session.stage.y ? session.stage.y.position - session.stage.y.lowerLimit : 0);
	let fovZ = $derived(session.stage.z ? session.stage.z.position - session.stage.z.lowerLimit : 0);
	let isXYMoving = $derived(session.stage.x?.isMoving || session.stage.y?.isMoving);
	let isZMoving = $derived(session.stage.z?.isMoving ?? false);
	let isStageMoving = $derived(isXYMoving || isZMoving);

	let primaryTile = $derived(session.selectedTiles[0] ?? null);
	let primaryStack = $derived(
		primaryTile ? (session.stacks.find((s) => s.row === primaryTile.row && s.col === primaryTile.col) ?? null) : null
	);

	let marginX = $derived(session.fov.width / 2);
	let marginY = $derived(session.fov.height / 2);

	let viewBoxWidth = $derived(session.stage.width + session.fov.width);
	let viewBoxHeight = $derived(session.stage.height + session.fov.height);
	let stageAspectRatio = $derived(viewBoxWidth / viewBoxHeight);
	let cornerLen = $derived(Math.min(session.fov.width, session.fov.height) / 8);

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
	let stagePixelsX = $derived(session.stage.width * scale);
	let stagePixelsY = $derived(session.stage.height * scale);

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
		return session.isTileSelected(tile.row, tile.col);
	}

	function handleTileSelect(e: MouseEvent, tile: Tile) {
		if (e.ctrlKey || e.metaKey) {
			if (session.isTileSelected(tile.row, tile.col)) session.removeFromSelection([[tile.row, tile.col]]);
			else session.addToSelection([[tile.row, tile.col]]);
		} else {
			session.selectTiles([[tile.row, tile.col]]);
		}
	}

	function clampToStageLimits(targetX: number, targetY: number): [number, number] {
		if (!session.stage.x || !session.stage.y) return [targetX, targetY];
		const minX = session.stage.x.lowerLimit;
		const maxX = session.stage.x.upperLimit;
		const minY = session.stage.y.lowerLimit;
		const maxY = session.stage.y.upperLimit;
		return [Math.max(minX, Math.min(maxX, targetX)), Math.max(minY, Math.min(maxY, targetY))];
	}

	function handleTileMove(e: MouseEvent, tile: Tile) {
		if (e.button !== 1) return;
		e.preventDefault();
		if (isXYMoving || !session.stage.x || !session.stage.y) return;
		const targetX = session.stage.x.lowerLimit + toMm(tile.x_um);
		const targetY = session.stage.y.lowerLimit + toMm(tile.y_um);
		const [clampedX, clampedY] = clampToStageLimits(targetX, targetY);
		session.stage.moveXY(clampedX, clampedY);
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
		if (isXYMoving || !session.stage.x || !session.stage.y) return;
		const targetX = session.stage.x.lowerLimit + toMm(stack.x_um);
		const targetY = session.stage.y.lowerLimit + toMm(stack.y_um);
		const [clampedX, clampedY] = clampToStageLimits(targetX, targetY);
		session.stage.moveXY(clampedX, clampedY);
	}

	function handleXSliderChange(e: Event) {
		if (!session.stage.x) return;
		const target = e.target as HTMLInputElement;
		session.stage.x.move(parseFloat(target.value));
	}

	function handleYSliderChange(e: Event) {
		if (!session.stage.y) return;
		const target = e.target as HTMLInputElement;
		session.stage.y.move(parseFloat(target.value));
	}

	function handleZSliderChange(e: Event) {
		if (!session.stage.z) return;
		const target = e.target as HTMLInputElement;
		session.stage.z.move(parseFloat(target.value));
	}

	function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFn();
		}
	}

	let gridLimX = $derived(session.fov.width * (1 - session.gridConfig.overlap));
	let gridLimY = $derived(session.fov.height * (1 - session.gridConfig.overlap));

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
		onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[tile.row, tile.col]]))}
	>
		<title>Tile [{tile.row}, {tile.col}]</title>
	</rect>
{/snippet}

{#snippet gridControls()}
	<div
		class="flex items-center gap-2 text-[0.65rem]"
		class:opacity-70={session.gridLocked}
		class:pointer-events-none={session.gridLocked}
	>
		<SpinBox
			value={session.gridConfig.x_offset_um / 1000}
			min={-gridLimX}
			max={gridLimX}
			step={0.1}
			snapValue={0.0}
			decimals={1}
			numCharacters={5}
			size="sm"
			prefix="Grid dX"
			suffix="mm"
			onChange={(value: number) => {
				if (session.gridLocked) return;
				session.setGridOffset(value * 1000, session.gridConfig.y_offset_um);
			}}
		/>
		<SpinBox
			value={session.gridConfig.y_offset_um / 1000}
			min={-gridLimY}
			max={gridLimY}
			snapValue={0.0}
			step={0.1}
			decimals={1}
			numCharacters={5}
			size="sm"
			prefix="Grid dY"
			suffix="mm"
			onChange={(value: number) => {
				if (session.gridLocked) return;
				session.setGridOffset(session.gridConfig.x_offset_um, value * 1000);
			}}
		/>
		<SpinBox
			value={session.gridConfig.overlap}
			min={0}
			max={0.5}
			snapValue={0.1}
			step={0.01}
			decimals={2}
			numCharacters={5}
			size="sm"
			prefix="Overlap"
			suffix="%"
			onChange={(value: number) => {
				if (session.gridLocked) return;
				session.setGridOverlap(value);
			}}
		/>
	</div>
{/snippet}
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
<div class="flex h-full w-full flex-col p-2">
	{#if session.stage.x && session.stage.y && session.stage.z}
		{@const layers: Layer[] = [
          { key: 'grid', color: 'text-blue-500', icon: 'lucide-lab:grid-lines', title: 'Toggle grid' },
          { key: 'stacks', color: 'text-blue-400', icon: 'ph:stack-light', title: 'Toggle stacks' },
          { key: 'path', color: 'text-slate-400', icon: 'iconoir:path-arrow', title: 'Toggle path' },
          { key: 'fov', color: 'text-success', icon: 'mdi:plus', title: 'Toggle FOV' },
      ]}
		<div class="flex flex-wrap items-center justify-between py-4">
			{@render gridControls()}
			<div class="flex gap-0.5 rounded p-1">
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
						min={session.stage.x?.lowerLimit}
						max={session.stage.x?.upperLimit}
						step={0.1}
						value={session.stage.x?.position}
						disabled={isXYMoving}
						oninput={handleXSliderChange}
					/>

					<div class="flex min-h-0 items-start">
						<input
							type="range"
							class="y-slider"
							style="height: {stagePixelsY}px; margin-top: {STAGE_BORDER + marginPixelsY}px;"
							min={session.stage.y?.lowerLimit}
							max={session.stage.y?.upperLimit}
							step={0.1}
							value={session.stage.y?.position}
							disabled={isXYMoving}
							oninput={handleYSliderChange}
						/>

						<svg
							viewBox="{-marginX} {-marginY} {viewBoxWidth} {viewBoxHeight}"
							class="xy-svg"
							style="width: {canvasWidth}px; height: {canvasHeight}px;"
						>
							{#if session.layerVisibility.stacks}
								<g class="stacks-layer">
									{#each session.stacks as stack (`${stack.row}_${stack.col}`)}
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
											onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[stack.row, stack.col]]))}
										>
											<title>Stack [{stack.row}, {stack.col}] - {stack.status} ({stack.num_frames} frames)</title>
										</rect>
									{/each}
								</g>
							{/if}

							{#if session.layerVisibility.path && session.stacks.length > 1}
								{@const pathPoints = session.stacks.map((s) => ({
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

							{#if session.layerVisibility.fov}
								{@const fovLeft = fovX - session.fov.width / 2}
								{@const fovTop = fovY - session.fov.height / 2}
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

									<rect
										x={fovLeft - 0.025}
										y={fovTop - 0.025}
										width={session.fov.width + 0.05}
										height={session.fov.height + 0.05}
										class="fov-rect"
										class:moving={isXYMoving}
									>
										<title>FOV: ({session.stage.x?.position.toFixed(1)}, {session.stage.y?.position.toFixed(1)}) mm</title>
									</rect>

									<g class="fov-crosshair" class:moving={isXYMoving}>
										<line x1={fovX - 0.3} y1={fovY} x2={fovX + 0.3} y2={fovY} />
										<line x1={fovX} y1={fovY - 0.3} x2={fovX} y2={fovY + 0.3} />
									</g>
								</g>
							{/if}

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
						min={session.stage.z?.lowerLimit}
						max={session.stage.z?.upperLimit}
						step={0.1}
						value={session.stage.z?.position}
						disabled={isZMoving}
						oninput={handleZSliderChange}
					/>
					<svg viewBox="0 0 30 {canvasHeight}" class="z-svg" preserveAspectRatio="none" width="100%" height="100%">
						{#if primaryStack && session.stage.z}
							{@const z0Offset = primaryStack.z_start_um / 1000 - session.stage.z.lowerLimit}
							{@const z1Offset = primaryStack.z_end_um / 1000 - session.stage.z.lowerLimit}
							{@const y0 = (1 - z0Offset / session.stage.depth) * canvasHeight - 1}
							{@const y1 = (1 - z1Offset / session.stage.depth) * canvasHeight - 1}
							<g class={getStackStatusColor(primaryStack.status)}>
								<line x1="0" y1={y0} x2="30" y2={y0} class="z-marker" />
								<line x1="0" {y1} x2="30" y2={y1} class="z-marker" />
							</g>
						{/if}
						<line
							x1="0"
							y1={(1 - fovZ / session.stage.depth) * canvasHeight - 1}
							x2="30"
							y2={(1 - fovZ / session.stage.depth) * canvasHeight - 1}
							class="z-line"
							class:moving={isZMoving}
						>
							<title>Z: {session.stage.z?.position.toFixed(1)} mm</title>
						</line>
					</svg>
				</div>
			</div>
		</div>

		<div class="flex items-center justify-between py-4">
			<div class="flex items-center gap-2">
				<SpinBox
					value={session.stage.x.position}
					min={session.stage.x.lowerLimit}
					max={session.stage.x.upperLimit}
					step={0.01}
					decimals={2}
					numCharacters={8}
					size="sm"
					prefix="X"
					suffix="mm"
					color={session.stage.x.isMoving ? 'var(--danger)' : undefined}
					onChange={(v) => session.stage.x && session.stage.x.move(v)}
				/>
				<SpinBox
					value={session.stage.y.position}
					min={session.stage.y.lowerLimit}
					max={session.stage.y.upperLimit}
					step={0.01}
					decimals={2}
					numCharacters={8}
					size="sm"
					prefix="Y"
					suffix="mm"
					color={session.stage.y.isMoving ? 'var(--danger)' : undefined}
					onChange={(v) => session.stage.y && session.stage.y.move(v)}
				/>
				<SpinBox
					value={session.stage.z.position}
					min={session.stage.z.lowerLimit}
					max={session.stage.z.upperLimit}
					step={0.001}
					decimals={3}
					numCharacters={8}
					size="sm"
					prefix="Z"
					suffix="mm"
					color={session.stage.z.isMoving ? 'var(--danger)' : undefined}
					onChange={(v) => session.stage.z && session.stage.z.move(v)}
				/>
			</div>
			<Button
				variant={isStageMoving ? 'danger' : 'outline'}
				size="sm"
				onclick={() => session.stage.halt()}
				disabled={!isStageMoving}
				aria-label="Halt stage"
			>
				Halt
			</Button>
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
