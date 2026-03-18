<script lang="ts" module>
	import type { LayerVisibility } from '$lib/main/types';

	let layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true, thumbnail: true });
</script>

<script lang="ts">
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type Tile, type StackStatus } from '$lib/main/types';
	import { ContextMenu, Dialog, SpinBox } from '$lib/ui/kit';
	import { onMount } from 'svelte';
	import { compositeFullFrames } from '$lib/main/preview.svelte.ts';
	import {
		GridLines,
		StackLight,
		PathArrow,
		Plus,
		ImageLight,
		Link,
		LinkOff,
		LockOutline,
		LockOpenOutline
	} from '$lib/icons';
	import { sanitizeString } from '$lib/utils';
	import type { Component } from 'svelte';
	import { watch } from 'runed';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	// ── Geometry ─────────────────────────────────────────────────────────

	const SLIDER_WIDTH = 16;
	const Z_AREA_WIDTH = SLIDER_WIDTH * 4;
	const STAGE_GAP = 16;
	const STAGE_BORDER = 0.5;

	const ARROW_HEAD = 'M -0.15 -0.2 L 0.15 0 L -0.15 0.2';
	const Z_SVG_WIDTH = 30;

	let isXYMoving = $derived(session.stage.x?.isMoving || session.stage.y?.isMoving);
	let isZMoving = $derived(session.stage.z?.isMoving ?? false);
	// let isPlanning = $derived(session.workflow.stepStates['plan'] === 'active');
	let isPlanning = true;

	let profileStacks = $derived(session.activeStacks);

	// FOV position relative to stage origin (lower limits)
	let fovX = $derived(session.stage.x ? session.stage.x.position - session.stage.x.lowerLimit : 0);
	let fovY = $derived(session.stage.y ? session.stage.y.position - session.stage.y.lowerLimit : 0);
	let fovZ = $derived(session.stage.z ? session.stage.z.position - session.stage.z.lowerLimit : 0);
	let fovLeft = $derived(fovX - session.fov.width / 2);
	let fovTop = $derived(fovY - session.fov.height / 2);

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
	let marginPixelsX = $derived(marginX * scale);
	let marginPixelsY = $derived(marginY * scale);
	let stagePixelsX = $derived(session.stage.width * scale);
	let stagePixelsY = $derived(session.stage.height * scale);
	let fovExtension = $derived(SLIDER_WIDTH / 2 / scale);

	let zLineY = $derived((1 - fovZ / session.stage.depth) * canvasHeight - 1);

	function updateCanvasSize(containerWidth: number, containerHeight: number) {
		const availableWidth = containerWidth - SLIDER_WIDTH / 2 - Z_AREA_WIDTH - STAGE_GAP - STAGE_BORDER * 2;
		const availableHeight = containerHeight - SLIDER_WIDTH / 2;
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

	watch(
		() => session.preview?.redrawGeneration,
		() => {
			fovNeedsRedraw = true;
		}
	);

	function fovFrameLoop() {
		if (fovNeedsRedraw && session.preview) {
			fovNeedsRedraw = false;
			const hasFrames = session.preview.channels.some((ch) => ch.visible && ch.frame);
			if (hasFrames) {
				compositeFullFrames(offscreenCtx, offscreen, session.preview.channels);
				thumbnail = offscreen.toDataURL('image/jpeg', 0.6);
			} else {
				thumbnail = '';
			}
		}
		fovAnimFrameId = requestAnimationFrame(fovFrameLoop);
	}

	// ── Slider targets ──────────────────────────────────────────────────

	let targetX = $state<number | null>(null);
	let targetY = $state<number | null>(null);
	let targetZ = $state<number | null>(null);

	function handleXInput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		targetX = v;
		session.stage.x?.move(v);
	}

	function handleYInput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		targetY = v;
		session.stage.y?.move(v);
	}

	function handleZInput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		targetZ = v;
		session.stage.z?.move(v);
	}

	// ── Interaction handlers ─────────────────────────────────────────────

	function toMm(um: number): number {
		return um / 1000;
	}

	function isSelected(tile: Tile): boolean {
		return session.isTileSelected(tile.row, tile.col);
	}

	function clampToStageLimits(x: number, y: number): [number, number] {
		if (!session.stage.x || !session.stage.y) return [x, y];
		return [
			Math.max(session.stage.x.lowerLimit, Math.min(session.stage.x.upperLimit, x)),
			Math.max(session.stage.y.lowerLimit, Math.min(session.stage.y.upperLimit, y))
		];
	}

	function moveToTilePosition(x_um: number, y_um: number) {
		if (isXYMoving || !session.stage.x || !session.stage.y) return;
		const tx = session.stage.x.lowerLimit + toMm(x_um);
		const ty = session.stage.y.lowerLimit + toMm(y_um);
		const [cx, cy] = clampToStageLimits(tx, ty);
		targetX = cx;
		targetY = cy;
		session.stage.moveXY(cx, cy);
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

	function toggleLayer(key: keyof LayerVisibility) {
		layerVisibility = { ...layerVisibility, [key]: !layerVisibility[key] };
	}

	const layers: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
		{ key: 'grid', color: 'text-info', Icon: GridLines, title: 'Toggle grid' },
		{ key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
		{ key: 'path', color: 'text-fg-muted', Icon: PathArrow, title: 'Toggle path' },
		{ key: 'fov', color: 'text-success', Icon: Plus, title: 'Toggle FOV' },
		{ key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
	];

	// ── Grid controls ───────────────────────────────────────────────────

	let gc = $derived(session.config.profiles[session.activeProfileId ?? '']?.grid ?? null);
	let hasStacks = $derived(session.activeStacks.length > 0);
	let gridForceUnlocked = $state(false);
	let gridEditable = $derived(!hasStacks || gridForceUnlocked);
	let gridLimX = $derived(session.fov.width * (1 - (gc?.overlap_x ?? 0.1)));
	let gridLimY = $derived(session.fov.height * (1 - (gc?.overlap_y ?? 0.1)));
	let activeProfileLabel = $derived(
		session.activeProfileId
			? (session.config.profiles[session.activeProfileId]?.label ?? sanitizeString(session.activeProfileId))
			: null
	);

	// Auto re-lock when profile changes or stacks increase
	watch(
		() => session.activeProfileId,
		() => {
			gridForceUnlocked = false;
		}
	);

	let prevStackCount = $state(0);
	watch(
		() => session.activeStacks.length,
		(count) => {
			if (count > prevStackCount) gridForceUnlocked = false;
			prevStackCount = count;
		}
	);

	let lockDialogOpen = $state(false);

	let offsetLinked = $state(false);
	let overlapLinked = $state(true);

	// ── Context menu ────────────────────────────────────────────────────

	type ContextTarget = { kind: 'tile'; tile: Tile } | { kind: 'empty'; x: number; y: number } | null;

	let contextTarget = $state<ContextTarget>(null);
	let zRangeBuffer = $state<{ zStartUm: number; zEndUm: number } | null>(null);
	let svgRef = $state<SVGSVGElement | null>(null);

	let contextTile = $derived(contextTarget?.kind === 'tile' ? contextTarget.tile : null);
	let contextStack = $derived(contextTile ? session.getStack(contextTile.row, contextTile.col) : null);
	let isMultiSelection = $derived(session.selectedTiles.length > 1);
	// Derived: how many selected tiles have/lack stacks
	let selectedWithStacks = $derived(session.selectedTiles.filter((t) => session.getStack(t.row, t.col)).length);
	let selectedWithoutStacks = $derived(session.selectedTiles.length - selectedWithStacks);

	const STACK_STATUSES: StackStatus[] = ['planned', 'completed', 'failed', 'skipped'];

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
		if (isXYMoving) return;
		if (contextTarget?.kind === 'tile') {
			moveToTilePosition(contextTarget.tile.x_um, contextTarget.tile.y_um);
		} else if (contextTarget?.kind === 'empty') {
			const [cx, cy] = clampToStageLimits(contextTarget.x, contextTarget.y);
			targetX = cx;
			targetY = cy;
			session.stage.moveXY(cx, cy);
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
		if (!contextStack) return;
		zRangeBuffer = { zStartUm: contextStack.z_start_um, zEndUm: contextStack.z_end_um };
	}

	function contextPasteZRange() {
		if (!zRangeBuffer) return;
		const edits = session.selectedTiles
			.filter((t) => session.getStack(t.row, t.col))
			.map((t) => ({ row: t.row, col: t.col, zStartUm: zRangeBuffer!.zStartUm, zEndUm: zRangeBuffer!.zEndUm }));
		if (edits.length > 0) session.editStacks(edits);
	}
</script>

{#snippet layerToggles()}
	<div class="flex gap-0.5">
		{#each layers as { key, color, Icon, title } (key)}
			{@const active = layerVisibility[key]}
			<button
				onclick={() => toggleLayer(key)}
				class="rounded p-1 transition-colors {active
					? `${color} hover:bg-element-hover`
					: 'text-fg-muted hover:text-fg hover:bg-element-hover'}"
				{title}
			>
				<Icon width="14" height="14" />
			</button>
		{/each}
	</div>
{/snippet}

{#snippet gridControls()}
	{#if gc}
		{@const size = 'xs'}
		{@const variant = 'ghost'}
		<div class="flex w-full items-center justify-between gap-4">
			<div class="flex items-center gap-1.5">
				<SpinBox
					{size}
					{variant}
					value={gc.x_offset_um / 1000}
					min={-gridLimX}
					max={gridLimX}
					step={0.1}
					snapValue={0.0}
					decimals={1}
					numCharacters={8}
					prefix="Offset X"
					suffix="mm"
					disabled={!gridEditable}
					onChange={(value) => {
						if (!gridEditable) return;
						const yMm = offsetLinked ? value : gc!.y_offset_um / 1000;
						session.setGridOffset(value * 1000, yMm * 1000, gridForceUnlocked);
					}}
				/>
				<button
					class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-5 w-5 items-center justify-center rounded transition-colors"
					title={offsetLinked ? 'Unlink offset X/Y' : 'Link offset X/Y'}
					onclick={() => {
						offsetLinked = !offsetLinked;
						if (offsetLinked && gc) {
							session.setGridOffset(gc.x_offset_um, gc.x_offset_um, gridForceUnlocked);
						}
					}}
				>
					{#if offsetLinked}
						<Link class="h-3 w-3" />
					{:else}
						<LinkOff class="h-3 w-3" />
					{/if}
				</button>
				<SpinBox
					{size}
					{variant}
					value={gc.y_offset_um / 1000}
					min={-gridLimY}
					max={gridLimY}
					snapValue={0.0}
					step={0.1}
					decimals={1}
					numCharacters={8}
					prefix="Offset Y"
					suffix="mm"
					disabled={!gridEditable}
					onChange={(value) => {
						if (!gridEditable) return;
						const xMm = offsetLinked ? value : gc!.x_offset_um / 1000;
						session.setGridOffset(xMm * 1000, value * 1000, gridForceUnlocked);
					}}
				/>
			</div>
			{#if activeProfileLabel}
				<div class="flex items-center gap-4 rounded-full bg-info/10 px-4 py-1">
					<span class="rounded-full text-xs font-medium tracking-wide text-nowrap text-info uppercase">
						{activeProfileLabel}
					</span>
					{#if hasStacks}
						<button
							class="transition-colors, flex cursor-pointer items-center justify-center rounded
							{gridForceUnlocked ? 'hover:bg-element-hover text-danger' : 'hover:bg-element-hover hover:text-fg text-warning'}"
							title={gridForceUnlocked ? 'Re-lock grid' : 'Unlock grid editing'}
							onclick={() => {
								if (gridForceUnlocked) {
									gridForceUnlocked = false;
								} else {
									lockDialogOpen = true;
								}
							}}
						>
							{#if gridForceUnlocked}
								<LockOpenOutline class="size-4" />
							{:else}
								<LockOutline class="size-4" />
							{/if}
						</button>
					{/if}
				</div>
			{/if}
			<div class="flex items-center gap-1.5">
				<SpinBox
					{size}
					{variant}
					value={gc.overlap_x}
					min={0}
					max={0.5}
					snapValue={0.1}
					step={0.01}
					decimals={2}
					numCharacters={8}
					prefix="Overlap X"
					suffix="%"
					disabled={!gridEditable}
					onChange={(value) => {
						if (!gridEditable) return;
						session.setGridOverlap(value, overlapLinked ? value : gc!.overlap_y, gridForceUnlocked);
					}}
				/>
				<button
					class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-5 w-5 items-center justify-center rounded transition-colors"
					title={overlapLinked ? 'Unlink overlap X/Y' : 'Link overlap X/Y'}
					onclick={() => {
						overlapLinked = !overlapLinked;
						if (overlapLinked && gc) {
							session.setGridOverlap(gc.overlap_x, gc.overlap_x, gridForceUnlocked);
						}
					}}
				>
					{#if overlapLinked}
						<Link class="h-3 w-3" />
					{:else}
						<LinkOff class="h-3 w-3" />
					{/if}
				</button>
				<SpinBox
					{size}
					{variant}
					value={gc.overlap_y}
					min={0}
					max={0.5}
					snapValue={0.1}
					step={0.01}
					decimals={2}
					numCharacters={8}
					prefix="Overlap Y"
					suffix="%"
					disabled={!gridEditable}
					onChange={(value) => {
						if (!gridEditable) return;
						session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value, gridForceUnlocked);
					}}
				/>
			</div>
		</div>
	{/if}
{/snippet}

{#snippet stageSlider(
	orientation: 'horizontal' | 'vertical-ltr' | 'vertical-rtl',
	min: number,
	max: number,
	value: number,
	disabled: boolean,
	oninput: (e: Event) => void,
	style: string
)}
	<div
		class="stage-slider"
		class:horizontal={orientation === 'horizontal'}
		class:vertical={orientation !== 'horizontal'}
		class:ltr={orientation === 'vertical-ltr'}
		class:rtl={orientation === 'vertical-rtl'}
		{style}
	>
		<input type="range" {min} {max} step={0.1} {value} {disabled} {oninput} />
	</div>
{/snippet}

<!-- ── SVG layer snippets ─────────────────────────────────────────────── -->

{#snippet stacksLayer()}
	{#if layerVisibility.stacks}
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
					class="nss stack outline-none {getStackStatusColor(stack.status)}"
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
	{/if}
{/snippet}

{#snippet pathLayer()}
	{#if layerVisibility.path && profileStacks.length > 1}
		{@const points = profileStacks.map((s) => ({ x: toMm(s.x_um), y: toMm(s.y_um) }))}
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
				<path
					d={ARROW_HEAD}
					stroke-width="1"
					class="nss fill-none opacity-70"
					transform="translate({midX}, {midY}) rotate({angle})"
				/>
			{/each}
		</g>
	{/if}
{/snippet}

{#snippet fovLayer()}
	{#if layerVisibility.fov}
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
		oncontextmenu={(e) => handleTileContext(e, tile)}
		onkeydown={(e) => handleKeydown(e, () => session.selectTiles([[tile.row, tile.col]]))}
	>
		<title>Tile [{tile.row}, {tile.col}]</title>
	</rect>
{/snippet}

{#snippet gridLayer()}
	{#if layerVisibility.grid}
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

{#snippet zAxisPanel()}
	<div
		class="hover:bg-canvas bg-elevated/50 relative border border-border transition-colors duration-300 ease-in-out"
		style="height: {canvasHeight}px; margin-top: {SLIDER_WIDTH / 2}px; width: {Z_AREA_WIDTH}px"
	>
		{@render stageSlider(
			'vertical-rtl',
			session.stage.z.lowerLimit,
			session.stage.z.upperLimit,
			isZMoving && targetZ !== null ? targetZ : session.stage.z.position,
			isZMoving,
			handleZInput,
			`position: absolute; inset: 0; z-index: 10; width: 100%; height: 100%; --slider-width: ${Z_AREA_WIDTH}px;`
		)}
		<svg
			viewBox="0 0 {Z_SVG_WIDTH} {canvasHeight}"
			class="z-svg pointer-none absolute inset-0 z-0"
			preserveAspectRatio="none"
			width="100%"
			height="100%"
		>
			{#if session.stage.z}
				{#each profileStacks as stack (`z_${stack.row}_${stack.col}`)}
					{@const selected = session.isTileSelected(stack.row, stack.col)}
					{@const z0Y =
						(1 - (stack.z_start_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
					{@const z1Y =
						(1 - (stack.z_end_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
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
			<text
				x={Z_SVG_WIDTH / 2}
				y="12"
				text-anchor="middle"
				class="text-fg-muted fill-current text-xs"
				transform="scale({Z_SVG_WIDTH / Z_AREA_WIDTH}, 1)"
			>
				Z axis
			</text>
			<line
				x1="0"
				y1={zLineY}
				x2={Z_SVG_WIDTH}
				y2={zLineY}
				class="nss z-line"
				class:moving={isZMoving}
				stroke-width="1"
				stroke={session.stage.z?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
			>
				<title>Z: {session.stage.z?.position.toFixed(1)} mm</title>
			</line>
		</svg>
	</div>
{/snippet}

<!-- ── Layout ─────────────────────────────────────────────────────────── -->

<div class="grid h-full w-full grid-rows-[auto_1fr_auto] gap-8">
	{#if session.stage.x && session.stage.y && session.stage.z}
		<div class="flex w-full items-center justify-between px-4 pt-4">
			{@render gridControls()}
		</div>
		<div class="grid flex-1 grid-rows-[1fr_auto] overflow-hidden px-4" bind:this={containerRef}>
			<div class="flex place-self-center" style:gap="{STAGE_GAP}px">
				<div
					class="grid"
					style="grid-template-columns: {SLIDER_WIDTH / 2}px auto; grid-template-rows: {SLIDER_WIDTH / 2}px 1fr;"
					style:--slider-width="{SLIDER_WIDTH}px"
				>
					{@render stageSlider(
						'horizontal',
						session.stage.x.lowerLimit,
						session.stage.x.upperLimit,
						session.stage.x.isMoving && targetX !== null ? targetX : session.stage.x.position,
						session.stage.x.isMoving,
						handleXInput,
						`grid-column: 2; width: ${stagePixelsX}px; height: ${SLIDER_WIDTH}px; margin-left: ${marginPixelsX + 0.5}px; transform: translateY(0.5px);`
					)}

					{@render stageSlider(
						'vertical-ltr',
						session.stage.y.lowerLimit,
						session.stage.y.upperLimit,
						session.stage.y.isMoving && targetY !== null ? targetY : session.stage.y.position,
						session.stage.y.isMoving,
						handleYInput,
						`grid-column: 1; grid-row: 2; width: ${SLIDER_WIDTH}px; height: ${stagePixelsY}px; margin-top: ${marginPixelsY}px; transform: translateX(0.5px);`
					)}

					<ContextMenu.Root>
						<ContextMenu.Trigger style="grid-column: 2; grid-row: 2;">
							<svg
								bind:this={svgRef}
								viewBox={viewBoxStr}
								class="border border-border"
								style="width: {canvasWidth}px; height: {canvasHeight}px;"
								overflow="visible"
								role="img"
								oncontextmenu={handleCanvasContext}
							>
								{#if layerVisibility.thumbnail && thumbnail}
									<image
										href={thumbnail}
										x={fovLeft}
										y={fovTop}
										width={session.fov.width}
										height={session.fov.height}
										preserveAspectRatio="xMidYMid slice"
										class="pointer-events-none"
									/>
								{/if}
								{@render fovLayer()}
								{@render gridLayer()}
								{@render stacksLayer()}
								{@render pathLayer()}
							</svg>
						</ContextMenu.Trigger>

						<ContextMenu.Content class="min-w-44">
							<ContextMenu.Item disabled={isXYMoving} onSelect={contextMoveHere}>Move here</ContextMenu.Item>

							{#if contextTile}
								<ContextMenu.Separator />
								<ContextMenu.Item onSelect={() => session.selectRow(contextTile!.row)}>
									Select row {contextTile.row}
								</ContextMenu.Item>
								<ContextMenu.Item onSelect={() => session.selectColumn(contextTile!.col)}>
									Select column {contextTile.col}
								</ContextMenu.Item>
							{/if}

							<ContextMenu.Separator />
							<ContextMenu.Item onSelect={() => session.selectAll()}>Select all</ContextMenu.Item>
							{#if session.selectedTiles.length > 0}
								<ContextMenu.Item onSelect={() => session.clearSelection()}>Deselect all</ContextMenu.Item>
							{/if}
							<ContextMenu.Item onSelect={() => session.invertSelection()}>Invert selection</ContextMenu.Item>

							{#if !contextTile}
								{#if profileStacks.length > 0 || session.tiles.length > 0}
									<ContextMenu.Separator />
								{/if}
								{#if profileStacks.length > 0}
									<ContextMenu.Item onSelect={() => session.selectWithStacks()}>Select with stacks</ContextMenu.Item>
								{/if}
								{#if session.tiles.length > 0}
									<ContextMenu.Item onSelect={() => session.selectWithoutStacks()}>
										Select without stacks
									</ContextMenu.Item>
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

							{#if contextTile && isPlanning}
								<ContextMenu.Separator />

								{#if !isMultiSelection}
									{#if !contextStack}
										<ContextMenu.Item onSelect={contextAddStack}>Add stack</ContextMenu.Item>
									{:else}
										<ContextMenu.Item onSelect={contextCopyZRange}>Copy Z range</ContextMenu.Item>
										{#if zRangeBuffer}
											<ContextMenu.Item onSelect={contextPasteZRange}>Paste Z range</ContextMenu.Item>
										{/if}
										<ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>
											Delete stack
										</ContextMenu.Item>
									{/if}
								{:else}
									{#if selectedWithoutStacks > 0}
										<ContextMenu.Item onSelect={contextAddStack}>
											Add stacks to selected ({selectedWithoutStacks})
										</ContextMenu.Item>
									{/if}
									{#if zRangeBuffer && selectedWithStacks > 0}
										<ContextMenu.Item onSelect={contextPasteZRange}>
											Paste Z range ({selectedWithStacks})
										</ContextMenu.Item>
									{/if}
									{#if selectedWithStacks > 0}
										<ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>
											Delete selected stacks ({selectedWithStacks})
										</ContextMenu.Item>
									{/if}
								{/if}
							{/if}
						</ContextMenu.Content>
					</ContextMenu.Root>
				</div>
				{@render zAxisPanel()}
			</div>
		</div>
		<div class="h-ui-xl flex w-full items-center justify-between border-t border-border px-4">
			{@render layerToggles()}
			{#if activeProfileLabel}
				<span class="text-fg-muted text-xs tracking-wide uppercase">{activeProfileLabel}</span>
			{/if}
		</div>
	{:else}
		<div class="grid flex-1 place-content-center">
			<p class="text-fg-muted text-base">Stage not available</p>
		</div>
	{/if}
</div>

<!-- Grid unlock confirmation dialog -->
<Dialog.Root bind:open={lockDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Unlock grid editing</Dialog.Title>
				<Dialog.Description>
					Stacks exist for this profile. Changing grid offset or overlap will recalculate stack positions. Continue?
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (lockDialogOpen = false)}
					class="text-fg-muted hover:bg-element-hover hover:text-fg rounded border border-border px-3 py-1.5 text-sm transition-colors"
				>
					Cancel
				</button>
				<button
					onclick={() => {
						gridForceUnlocked = true;
						lockDialogOpen = false;
					}}
					class="rounded bg-warning px-3 py-1.5 text-sm text-warning-fg transition-colors hover:bg-warning/90"
				>
					Unlock
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

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
			stroke: var(--color-zinc-400);
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

	/* Stage sliders */

	.stage-slider {
		position: relative;
	}

	.stage-slider input {
		-webkit-appearance: none;
		appearance: none;
		cursor: pointer;
		margin: 0;
		padding: 0;
		border: none;
		background-color: transparent;
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		--_track-color: var(--color-zinc-700);
		--_track-width: 1px;

		&:hover {
			--_track-color: var(--color-zinc-500);
		}

		&::-webkit-slider-runnable-track {
			background: var(--_track-bg, transparent);
			border-radius: 0;
		}
		&::-moz-range-track {
			background: var(--_track-bg, transparent);
			border-radius: 0;
		}
		&::-webkit-slider-thumb {
			-webkit-appearance: none;
			appearance: none;
			inline-size: 1px;
			block-size: var(--slider-width);
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&::-moz-range-thumb {
			appearance: none;
			inline-size: 1px;
			block-size: var(--slider-width);
			border: none;
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&:disabled {
			cursor: not-allowed;
			&::-webkit-slider-thumb {
				background: var(--color-danger);
			}
			&::-moz-range-thumb {
				background: var(--color-danger);
			}
		}
	}

	.horizontal input {
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / 100% var(--_track-width) no-repeat;
	}

	.vertical input {
		writing-mode: vertical-rl;
	}

	.ltr input {
		direction: ltr;
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / var(--_track-width) 100% no-repeat;
	}

	.rtl input {
		direction: rtl;
	}
</style>
