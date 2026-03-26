<script lang="ts" module>
	import type { LayerVisibility } from '$lib/main/types';
	import { GridLines, StackLight, ImageLight } from '$lib/icons';
	import type { Component } from 'svelte';

	let layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true, thumbnail: true });

	function toggleLayer(key: keyof LayerVisibility) {
		layerVisibility = { ...layerVisibility, [key]: !layerVisibility[key] };
	}

	const layers: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
		{ key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
		{ key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
		{ key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
	];
</script>

<script lang="ts">
	import type { Session } from '$lib/main';
	import { type Tile, type Stack, type StackStatus } from '$lib/main/types';
	import { ContextMenu } from '$lib/ui/kit';
	import { onMount } from 'svelte';
	import { createFovThumbnail } from '../grid.svelte';
	import GridControls from './GridControls.svelte';
	import StageSlider from '../StageSlider.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	// ── Geometry ─────────────────────────────────────────────────────────

	const SLIDER_WIDTH = 16;
	const Z_AREA_WIDTH = SLIDER_WIDTH * 4;
	const STAGE_GAP = 16;
	const STAGE_BORDER = 0.5;

	const Z_SVG_WIDTH = 30;

	let isXYMoving = $derived(session.stage.x?.isMoving || session.stage.y?.isMoving);
	let isAcquiring = $derived(session.mode === 'acquiring');

	let profileStacks = $derived(session.activeStacks);

	// FOV position relative to stage origin (lower limits)
	let fovX = $derived(session.stage.x ? session.stage.x.position - session.stage.x.lowerLimit : 0);
	let fovY = $derived(session.stage.y ? session.stage.y.position - session.stage.y.lowerLimit : 0);
	let fovZ = $derived(session.stage.z ? session.stage.z.position - session.stage.z.lowerLimit : 0);

	// ViewBox: stage bounds + one FOV of margin on each side
	let marginX = $derived(session.fov.width / 2);
	let marginY = $derived(session.fov.height / 2);
	let viewBoxWidth = $derived(session.stage.width + session.fov.width);
	let viewBoxHeight = $derived(session.stage.height + session.fov.height);
	let viewBoxStr = $derived(`${-marginX} ${-marginY} ${viewBoxWidth} ${viewBoxHeight}`);

	// ── Canvas sizing ────────────────────────────────────────────────────

	let containerRef = $state<HTMLDivElement | null>(null);
	let canvasWidth = $state(400);
	let canvasHeight = $state(250);

	let stageAspectRatio = $derived(viewBoxWidth / viewBoxHeight);
	let scale = $derived(canvasWidth / viewBoxWidth);
	let stagePixelsX = $derived(session.stage.width * scale);
	let stagePixelsY = $derived(session.stage.height * scale);

	let xSliderStyle = $derived(
		`left: ${marginX * scale}px; top: ${-SLIDER_WIDTH / 2}px; width: ${stagePixelsX}px; height: ${SLIDER_WIDTH}px;`
	);
	let ySliderStyle = $derived(
		`left: ${-SLIDER_WIDTH / 2}px; top: ${marginY * scale}px; width: ${SLIDER_WIDTH}px; height: ${stagePixelsY}px;`
	);

	let fovExtension = $derived(SLIDER_WIDTH / 2 / scale);
	let zLineY = $derived((1 - fovZ / session.stage.depth) * canvasHeight - 1);

	function updateCanvasSize(containerWidth: number, containerHeight: number) {
		const availableWidth = containerWidth - Z_AREA_WIDTH - STAGE_GAP - STAGE_BORDER * 2;
		const availableHeight = containerHeight;
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

		return () => {
			resizeObserver.disconnect();
		};
	});

	$effect(() => {
		if (containerRef) {
			const { width, height } = containerRef.getBoundingClientRect();
			updateCanvasSize(width, height);
		}
	});

	// ── FOV thumbnail ────────────────────────────────────────────────────

	const { thumbnail } = createFovThumbnail(() => session);

	// ── Slider targets ──────────────────────────────────────────────────

	let targetX = $state<number | null>(null);
	let targetY = $state<number | null>(null);
	let targetZ = $state<number | null>(null);

	// ── Interaction handlers ─────────────────────────────────────────────

	function toMm(um: number): number {
		return um / 1000;
	}

	function moveToTilePosition(x_um: number, y_um: number) {
		if (isXYMoving || !session.stage.x || !session.stage.y) return;
		const tx = session.stage.x.lowerLimit + toMm(x_um);
		const ty = session.stage.y.lowerLimit + toMm(y_um);
		targetX = tx;
		targetY = ty;
		session.stage.moveXY(tx, ty);
	}

	function handleTileSelect(e: MouseEvent, tile: Tile) {
		if (e.ctrlKey || e.metaKey) {
			if (session.isTileSelected(tile.row, tile.col)) session.removeFromSelection([[tile.row, tile.col]]);
			else session.addToSelection([[tile.row, tile.col]]);
		} else {
			session.selectTiles([[tile.row, tile.col]]);
		}
	}

	function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			selectFn();
		}
	}

	// ── Context menu ────────────────────────────────────────────────────

	type ContextTarget = { kind: 'tile'; tile: Tile } | { kind: 'empty'; x: number; y: number } | null;

	type MenuContext =
		| { kind: 'empty'; x: number; y: number }
		| { kind: 'single'; tile: Tile; stack: Stack | null }
		| { kind: 'multi'; tile: Tile; withStacks: number; withoutStacks: number };

	let contextTarget = $state<ContextTarget>(null);
	let zRangeBuffer = $state<{ zStartUm: number; zEndUm: number } | null>(null);
	let svgRef = $state<SVGSVGElement | null>(null);

	const STACK_STATUSES: StackStatus[] = ['planned', 'completed', 'failed', 'skipped'];

	let menuContext = $derived.by((): MenuContext | null => {
		if (!contextTarget) return null;
		if (contextTarget.kind === 'empty') return contextTarget;
		const tile = contextTarget.tile;
		const selected = session.selectedTiles;
		if (selected.length <= 1) {
			return { kind: 'single', tile, stack: session.getStack(tile.row, tile.col) ?? null };
		}
		const withStacks = selected.filter((t) => session.getStack(t.row, t.col)).length;
		return { kind: 'multi', tile, withStacks, withoutStacks: selected.length - withStacks };
	});

	function handleTileContext(e: MouseEvent, tile: Tile) {
		if (!session.isTileSelected(tile.row, tile.col)) {
			session.selectTiles([[tile.row, tile.col]]);
		}
		contextTarget = { kind: 'tile', tile };
	}

	function handleCanvasContext(e: MouseEvent) {
		if (e.target !== svgRef) return;
		if (!svgRef || !session.stage.x || !session.stage.y) return;
		const ctm = svgRef.getScreenCTM()?.inverse();
		if (!ctm) return;
		const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm);
		contextTarget = {
			kind: 'empty',
			x: session.stage.x.lowerLimit + pt.x,
			y: session.stage.y.lowerLimit + pt.y
		};
	}

	function contextMoveHere() {
		if (isXYMoving || !menuContext) return;
		if (menuContext.kind === 'empty') {
			targetX = menuContext.x;
			targetY = menuContext.y;
			session.stage.moveXY(menuContext.x, menuContext.y);
		} else {
			moveToTilePosition(menuContext.tile.x_um, menuContext.tile.y_um);
		}
	}

	function contextAddStack() {
		const gc = session.gridConfig;
		if (!gc) return;
		const tiles = session.selectedTiles.filter((t) => !session.getStack(t.row, t.col));
		if (tiles.length === 0) return;
		session.addStacks(
			tiles.map((t) => ({
				row: t.row,
				col: t.col,
				zStartUm: gc.default_z_start_um,
				zEndUm: gc.default_z_end_um
			}))
		);
	}

	function contextDeleteStack() {
		const tiles = session.selectedTiles.filter((t) => session.getStack(t.row, t.col));
		if (tiles.length === 0) return;
		session.removeStacks(tiles.map((t) => ({ row: t.row, col: t.col })));
	}

	function contextCopyZRange() {
		if (menuContext?.kind !== 'single' || !menuContext.stack) return;
		zRangeBuffer = { zStartUm: menuContext.stack.z_start_um, zEndUm: menuContext.stack.z_end_um };
	}

	function contextPasteZRange() {
		if (!zRangeBuffer) return;
		const edits = session.selectedTiles
			.filter((t) => session.getStack(t.row, t.col))
			.map((t) => ({ row: t.row, col: t.col, zStartUm: zRangeBuffer!.zStartUm, zEndUm: zRangeBuffer!.zEndUm }));
		if (edits.length > 0) session.editStacks(edits);
	}
</script>

{#snippet fovLayer()}
	{#if layerVisibility.thumbnail && thumbnail}
		<image
			href={thumbnail}
			x={fovX - session.fov.width / 2}
			y={fovY - session.fov.height / 2}
			width={session.fov.width}
			height={session.fov.height}
			preserveAspectRatio="xMidYMid slice"
			class="pointer-events-none"
		/>
	{/if}
	<g class="fov-layer pointer-events-none">
		<line
			class="nss"
			x1={-marginX - fovExtension}
			y1={fovY}
			x2={-marginX + viewBoxWidth}
			y2={fovY}
			stroke-width="1"
			stroke={session.stage.y?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
		/>
		<line
			class="nss"
			x1={fovX}
			y1={-marginY - fovExtension}
			x2={fovX}
			y2={-marginY + viewBoxHeight}
			stroke-width="1"
			stroke={session.stage.x?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
		/>
	</g>
{/snippet}

{#snippet gridLayer()}
	{#if layerVisibility.grid}
		{@const sortedTiles = [...session.tiles].sort(
			(a, b) => Number(session.isTileSelected(a.row, a.col)) - Number(session.isTileSelected(b.row, b.col))
		)}
		<g class="grid-layer">
			{#each sortedTiles as tile (`${tile.row}_${tile.col}`)}
				{@const selected = session.isTileSelected(tile.row, tile.col)}
				{@const cx = toMm(tile.x_um)}
				{@const cy = toMm(tile.y_um)}
				{@const w = toMm(tile.w_um)}
				{@const h = toMm(tile.h_um)}
				<rect
					x={cx - w / 2}
					y={cy - h / 2}
					width={w}
					height={h}
					class="nss fill-transparent transition-colors outline-none hover:fill-fg-muted/15 {selected
						? 'stroke-warning/50 '
						: 'stroke-border'}"
					stroke-width={1}
					stroke-dasharray=""
					stroke-linecap="round"
					class:cursor-pointer={!isXYMoving}
					class:cursor-not-allowed={isXYMoving}
					role="button"
					tabindex={isXYMoving ? -1 : 0}
					onclick={(e) => handleTileSelect(e, tile)}
					oncontextmenu={(e) => handleTileContext(e, tile)}
					onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[tile.row, tile.col]]))}
				>
					<title>Tile [{tile.row}, {tile.col}]</title>
				</rect>
			{/each}
		</g>
	{/if}
{/snippet}

{#snippet stacksLayer()}
	{#if layerVisibility.stacks}
		{@const points = profileStacks.map((s) => ({ x: toMm(s.x_um), y: toMm(s.y_um) }))}
		<g class="stacks-layer">
			{#each profileStacks as stack (`${stack.row}_${stack.col}`)}
				{@const cx = toMm(stack.x_um)}
				{@const cy = toMm(stack.y_um)}
				{@const w = toMm(stack.w_um)}
				{@const h = toMm(stack.h_um)}
				<rect
					x={cx - w / 2}
					y={cy - h / 2}
					width={w}
					height={h}
					data-stack-status={stack.status}
					class="nss fill-current text-(--stack-status) transition-[fill-opacity] duration-300 outline-none [fill-opacity:0.2] hover:[fill-opacity:0.3]"
					class:cursor-pointer={!isXYMoving}
					class:cursor-not-allowed={isXYMoving}
					role="button"
					tabindex={isXYMoving ? -1 : 0}
					onclick={(e) => handleTileSelect(e, stack)}
					oncontextmenu={(e) => handleTileContext(e, stack)}
					onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[stack.row, stack.col]]))}
				>
					<title>Stack [{stack.row}, {stack.col}] - {stack.status} ({stack.num_frames} frames)</title>
				</rect>
			{/each}
		</g>
		<g class="pointer-none text-fg-muted" stroke="currentColor" stroke-linecap="square">
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
				{@const arrowHead = 'M -0.15 -0.2 L 0.15 0 L -0.15 0.2'}
				<path
					d={arrowHead}
					stroke-width="1"
					class="nss fill-none opacity-70"
					transform="translate({midX}, {midY}) rotate({angle})"
				/>
			{/each}
		</g>
	{/if}
{/snippet}

{#snippet contextMenuItems()}
	{#if isAcquiring}
		<ContextMenu.Item disabled>Acquisition in progress</ContextMenu.Item>
	{:else}
		<!-- Navigation -->
		<ContextMenu.Item disabled={isXYMoving} onSelect={contextMoveHere}>Move here</ContextMenu.Item>

		<!-- Row/Column selection (tile contexts only) -->
		{#if menuContext?.kind === 'single' || menuContext?.kind === 'multi'}
			<ContextMenu.Separator />
			<ContextMenu.Item onSelect={() => session.selectRow(menuContext.tile.row)}>
				Select row {menuContext.tile.row}
			</ContextMenu.Item>
			<ContextMenu.Item onSelect={() => session.selectColumn(menuContext.tile.col)}>
				Select column {menuContext.tile.col}
			</ContextMenu.Item>
		{/if}

		<!-- Selection actions -->
		<ContextMenu.Separator />
		<ContextMenu.Item onSelect={() => session.selectAll()}>Select all</ContextMenu.Item>
		{#if session.selectedTiles.length > 0}
			<ContextMenu.Item onSelect={() => session.clearSelection()}>Deselect all</ContextMenu.Item>
		{/if}
		<ContextMenu.Item onSelect={() => session.invertSelection()}>Invert selection</ContextMenu.Item>

		<!-- Bulk selection (empty canvas only) -->
		{#if menuContext?.kind === 'empty'}
			{#if profileStacks.length > 0 || session.tiles.length > 0}
				<ContextMenu.Separator />
			{/if}
			{#if profileStacks.length > 0}
				<ContextMenu.Item onSelect={() => session.selectWithStacks()}>Select with stacks</ContextMenu.Item>
			{/if}
			{#if session.tiles.length > 0}
				<ContextMenu.Item onSelect={() => session.selectWithoutStacks()}>Select without stacks</ContextMenu.Item>
			{/if}
			{#if profileStacks.length > 0}
				<ContextMenu.Sub>
					<ContextMenu.SubTrigger>Select by status</ContextMenu.SubTrigger>
					<ContextMenu.SubContent>
						{#each STACK_STATUSES as status (status)}
							<ContextMenu.Item onSelect={() => session.selectByStackStatus(status)}>
								{status[0].toUpperCase() + status.slice(1)}
							</ContextMenu.Item>
						{/each}
					</ContextMenu.SubContent>
				</ContextMenu.Sub>
			{/if}
		{/if}

		<!-- Stack operations -->
		{#if menuContext?.kind === 'single'}
			<ContextMenu.Separator />
			{#if !menuContext.stack}
				<ContextMenu.Item onSelect={contextAddStack}>Add stack</ContextMenu.Item>
			{:else}
				<ContextMenu.Sub>
					<ContextMenu.SubTrigger>Z range</ContextMenu.SubTrigger>
					<ContextMenu.SubContent>
						<ContextMenu.Item onSelect={contextCopyZRange}>Copy</ContextMenu.Item>
						{#if zRangeBuffer}
							<ContextMenu.Item onSelect={contextPasteZRange}>Paste</ContextMenu.Item>
						{/if}
					</ContextMenu.SubContent>
				</ContextMenu.Sub>
				<ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>Delete stack</ContextMenu.Item>
			{/if}
		{:else if menuContext?.kind === 'multi'}
			<ContextMenu.Separator />
			{#if menuContext.withoutStacks > 0}
				<ContextMenu.Item onSelect={contextAddStack}>
					Add stacks to selected ({menuContext.withoutStacks})
				</ContextMenu.Item>
			{/if}
			{#if zRangeBuffer && menuContext.withStacks > 0}
				<ContextMenu.Item onSelect={contextPasteZRange}>
					Paste Z range ({menuContext.withStacks})
				</ContextMenu.Item>
			{/if}
			{#if menuContext.withStacks > 0}
				<ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>
					Delete selected stacks ({menuContext.withStacks})
				</ContextMenu.Item>
			{/if}
		{/if}
	{/if}
{/snippet}

{#if session.stage.x && session.stage.y && session.stage.z}
	<div class="flex h-full flex-col-reverse">
		<div class="flex w-full items-center justify-between px-4 py-4">
			<GridControls {session} />
		</div>
		<div class="grid flex-1 place-content-center overflow-hidden px-4 py-8" bind:this={containerRef}>
			<div class="flex" style:gap="{STAGE_GAP}px">
				<div class="relative" style="width: {canvasWidth}px; height: {canvasHeight}px;">
					<p class="absolute -bottom-5 left-0 text-xs text-fg-muted">X / Y</p>
					<StageSlider
						axis={session.stage.x}
						orientation="horizontal"
						bind:target={targetX}
						thumbLengthPx={SLIDER_WIDTH}
						class="absolute z-10"
						style={xSliderStyle}
					/>

					<StageSlider
						axis={session.stage.y}
						orientation="vertical-ltr"
						bind:target={targetY}
						thumbLengthPx={SLIDER_WIDTH}
						class="absolute z-10"
						style={ySliderStyle}
					/>
					<div class="absolute -bottom-8 flex h-ui-md w-full items-center justify-center gap-0.5">
						{#each layers as { key, color, Icon, title } (key)}
							{@const active = layerVisibility[key]}
							<button
								onclick={() => toggleLayer(key)}
								class="cursor-pointer rounded-full p-1.5 transition-colors {active ? `${color} ` : 'text-fg-faint'}"
								{title}
							>
								<Icon width="14" height="14" />
							</button>
						{/each}
					</div>
					<ContextMenu.Root>
						<ContextMenu.Trigger>
							<svg
								bind:this={svgRef}
								viewBox={viewBoxStr}
								class="border border-border"
								style="width: {canvasWidth}px; height: {canvasHeight}px;"
								overflow="visible"
								role="img"
								oncontextmenu={handleCanvasContext}
							>
								{@render fovLayer()}
								{@render gridLayer()}
								{@render stacksLayer()}
							</svg>
						</ContextMenu.Trigger>

						<ContextMenu.Content class="min-w-44">
							{@render contextMenuItems()}
						</ContextMenu.Content>
					</ContextMenu.Root>
				</div>
				<!-- Z axis panel -->
				<div
					class="relative border border-border bg-elevated/50 transition-colors duration-300 ease-in-out hover:bg-elevated/75"
					style="height: {canvasHeight}px; width: {Z_AREA_WIDTH}px"
				>
					<p class="absolute right-0 -bottom-5 w-full text-center text-xs text-fg-muted">Z</p>
					<StageSlider
						axis={session.stage.z}
						orientation="vertical-rtl"
						thumbLengthPx={Z_AREA_WIDTH}
						bind:target={targetZ}
						class="absolute inset-0 z-10 h-full w-full"
					/>
					<svg
						viewBox="0 0 {Z_SVG_WIDTH} {canvasHeight}"
						class="pointer-none absolute inset-0 z-0"
						preserveAspectRatio="none"
						width="100%"
						height="100%"
					>
						{#each profileStacks as stack (`z_${stack.row}_${stack.col}`)}
							{@const selected = session.isTileSelected(stack.row, stack.col)}
							{@const z0Y =
								(1 - (stack.z_start_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
							{@const z1Y =
								(1 - (stack.z_end_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
							<g
								data-stack-status={stack.status}
								class="text-(--stack-status)"
								stroke-width={selected ? '1.5' : '0.5'}
								stroke="currentColor"
								opacity={selected ? 1 : 0.3}
							>
								<line class="nss" x1="0" y1={z0Y} x2={Z_SVG_WIDTH} y2={z0Y} />
								<line class="nss" x1="0" y1={z1Y} x2={Z_SVG_WIDTH} y2={z1Y} />
							</g>
						{/each}
						<line
							x1="0"
							y1={zLineY}
							x2={Z_SVG_WIDTH}
							y2={zLineY}
							class="nss"
							stroke-width="1"
							stroke={session.stage.z?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
						>
							<title>Z: {session.stage.z?.position.toFixed(1)} mm</title>
						</line>
					</svg>
				</div>
			</div>
		</div>
	</div>
{:else}
	<div class="grid h-full w-full place-content-center">
		<p class="text-base text-fg-muted">Stage not available</p>
	</div>
{/if}

<style>
	/* SVG elements */

	.nss {
		vector-effect: non-scaling-stroke;
	}
</style>
