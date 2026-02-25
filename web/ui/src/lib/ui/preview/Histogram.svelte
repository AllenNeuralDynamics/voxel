<script lang="ts">
	import { ContextMenu } from 'bits-ui';
	import { computeAutoLevels } from '$lib/utils';
	import ColormapPicker from './ColormapPicker.svelte';
	import Icon from '@iconify/svelte';
	import type { ColormapCatalog } from '$lib/main';

	interface Props {
		label: string;
		histData: number[] | null;
		levelsMin: number;
		levelsMax: number;
		onLevelsChange: (min: number, max: number) => void;
		colormap: string | null;
		catalog: ColormapCatalog;
		onColormapChange: (colormap: string) => void;
		dataTypeMax?: number;
		visible?: boolean;
		onVisibilityChange?: (visible: boolean) => void;
	}

	let {
		label,
		histData: histogram,
		levelsMin,
		levelsMax,
		onLevelsChange,
		colormap,
		catalog,
		onColormapChange,
		dataTypeMax = 65535,
		visible,
		onVisibilityChange
	}: Props = $props();

	// ── Colormap Colors ────────────────────────────────────────────────

	const gradientId = `ch-grad-${crypto.randomUUID().slice(0, 8)}`;

	const colors = $derived.by(() => {
		if (!colormap) return ['#06b6d4'];
		if (colormap.startsWith('#')) return [colormap];
		for (const group of catalog) {
			const stops = group.colormaps[colormap];
			if (stops) return stops;
		}
		return ['#06b6d4'];
	});

	// ── Display Window ─────────────────────────────────────────────────

	let windowMin = $state(0);
	let windowMax = $state(0);
	let hasAutoFit = $state(false);
	let prevDTMax = -1;

	$effect.pre(() => {
		if (dataTypeMax !== prevDTMax) {
			windowMin = 0;
			windowMax = dataTypeMax;
			hasAutoFit = false;
			prevDTMax = dataTypeMax;
		}
	});

	const hasValidData = $derived(!!histogram && histogram.length > 0);
	const numBins = $derived(histogram?.length || 1);
	const startBin = $derived(Math.floor((windowMin / dataTypeMax) * (numBins - 1)));
	const endBin = $derived(Math.ceil((windowMax / dataTypeMax) * (numBins - 1)));

	// ── Levels ─────────────────────────────────────────────────────────

	const minBin = $derived(Math.round(levelsMin * (numBins - 1)));
	const maxBin = $derived(Math.round(levelsMax * (numBins - 1)));
	const minIntensity = $derived(Math.round(levelsMin * dataTypeMax));
	const maxIntensity = $derived(Math.round(levelsMax * dataTypeMax));

	// ── Histogram SVG ─────────────────────────────────────────────────

	let svgWidth = $state(256);
	const svgHeight = 24;

	const displayHist = $derived.by(() => {
		if (!hasValidData || !histogram) return [];
		const slice = histogram.slice(startBin, endBin + 1);
		const peak = Math.max(...slice);
		if (peak === 0) return slice.map(() => 0);
		return slice.map((c) => c / peak);
	});

	function binToX(bin: number): number {
		if (endBin === startBin) return 0;
		if (bin <= startBin) return 0;
		if (bin >= endBin) return svgWidth;
		return ((bin - startBin) / (endBin - startBin)) * svgWidth;
	}

	const minHandleX = $derived(binToX(minBin));
	const maxHandleX = $derived(Math.min(binToX(maxBin), svgWidth - 2));

	const bgPoints = $derived.by(() => {
		if (displayHist.length === 0) return '';
		return displayHist
			.map((v, i) => {
				const x = (i / (displayHist.length - 1 || 1)) * svgWidth;
				const y = svgHeight - v * svgHeight;
				return `${x},${y}`;
			})
			.join(' ');
	});

	const fgEntries = $derived.by(() => {
		if (displayHist.length === 0) return [];
		return displayHist
			.map((v, i) => {
				const actualBin = startBin + i;
				if (actualBin >= minBin && actualBin <= maxBin) {
					const x = (i / (displayHist.length - 1 || 1)) * svgWidth;
					const y = svgHeight - v * svgHeight;
					return { x, y };
				}
				return null;
			})
			.filter((p): p is { x: number; y: number } => p !== null);
	});

	const fgPoints = $derived(fgEntries.map((p) => `${p.x},${p.y}`).join(' '));

	const fgPolygon = $derived.by(() => {
		if (fgEntries.length < 2) return '';
		const first = fgEntries[0];
		const last = fgEntries[fgEntries.length - 1];
		return `${first.x},${svgHeight} ${fgEntries.map((p) => `${p.x},${p.y}`).join(' ')} ${last.x},${svgHeight}`;
	});

	// ── Drag Interaction ──────────────────────────────────────────────

	let dragging = $state<'min' | 'max' | null>(null);

	function xToLevel(clientX: number, rect: DOMRect): number {
		const x = Math.max(0, Math.min(svgWidth, clientX - rect.left));
		const rel = x / svgWidth;
		const bin = startBin + rel * (endBin - startBin);
		return bin / (numBins - 1);
	}

	function onHandleDown(e: PointerEvent, handle: 'min' | 'max') {
		e.preventDefault();
		(e.currentTarget as SVGElement).setPointerCapture(e.pointerId);
		dragging = handle;
	}

	function onHandleMove(e: PointerEvent) {
		if (!dragging) return;
		const svg = (e.currentTarget as SVGElement).closest('svg');
		if (!svg) return;
		const level = xToLevel(e.clientX, svg.getBoundingClientRect());

		if (dragging === 'min') {
			onLevelsChange(Math.max(0, Math.min(level, levelsMax - 0.001)), levelsMax);
		} else {
			onLevelsChange(levelsMin, Math.min(1, Math.max(level, levelsMin + 0.001)));
		}
	}

	function onHandleUp(e: PointerEvent) {
		(e.currentTarget as SVGElement).releasePointerCapture(e.pointerId);
		dragging = null;
	}

	// ── Auto Fit & Auto Levels ────────────────────────────────────────

	function autoFit() {
		if (!hasValidData || !histogram) return;
		let lo = 0;
		let hi = numBins - 1;
		for (let i = 0; i < numBins; i++) {
			if (histogram[i] > 0) {
				lo = i;
				break;
			}
		}
		for (let i = numBins - 1; i >= 0; i--) {
			if (histogram[i] > 0) {
				hi = i;
				break;
			}
		}
		const pad = (hi - lo) * 0.15;
		windowMin = Math.round((Math.max(0, lo - pad) / (numBins - 1)) * dataTypeMax);
		windowMax = Math.round((Math.min(numBins - 1, hi + pad) / (numBins - 1)) * dataTypeMax);
		hasAutoFit = true;
	}

	$effect(() => {
		if (hasValidData && !hasAutoFit) autoFit();
	});

	function autoLevels() {
		if (!hasValidData || !histogram) return;
		const result = computeAutoLevels(histogram);
		if (result) onLevelsChange(result.min, result.max);
	}

	// ── Scroll-to-Zoom ───────────────────────────────────────────────

	let histContainerEl = $state<HTMLElement | null>(null);

	function onHistWheel(e: WheelEvent) {
		e.preventDefault();

		const range = windowMax - windowMin;
		const zoomFactor = e.deltaY > 0 ? 1.15 : 0.85;
		const newRange = Math.max(range * zoomFactor, dataTypeMax * 0.01);

		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const mouseRel = (e.clientX - rect.left) / rect.width;
		const pivot = windowMin + range * mouseRel;

		windowMin = Math.max(0, Math.round(pivot - newRange * mouseRel));
		windowMax = Math.min(dataTypeMax, Math.round(pivot + newRange * (1 - mouseRel)));
	}

	$effect(() => {
		if (!histContainerEl) return;
		histContainerEl.addEventListener('wheel', onHistWheel, { passive: false });
		return () => histContainerEl?.removeEventListener('wheel', onHistWheel);
	});

	// ── Floating Level Inputs ─────────────────────────────────────────

	const labelWidth = 36;
	const labelGap = 4;

	function commitFloatingInput(e: Event, handle: 'min' | 'max') {
		const val = parseInt((e.target as HTMLInputElement).value);
		if (isNaN(val)) return;
		if (handle === 'min') {
			onLevelsChange(Math.max(0, Math.min(val, maxIntensity - 1)) / dataTypeMax, levelsMax);
		} else {
			onLevelsChange(levelsMin, Math.min(dataTypeMax, Math.max(val, minIntensity + 1)) / dataTypeMax);
		}
	}

	function commitWindowInput(e: Event, bound: 'min' | 'max') {
		const val = parseInt((e.target as HTMLInputElement).value);
		if (isNaN(val)) return;
		if (bound === 'min') {
			windowMin = Math.max(0, Math.min(val, windowMax - 1));
		} else {
			windowMax = Math.min(dataTypeMax, Math.max(val, windowMin + 1));
		}
	}

	const labelPositions = $derived.by(() => {
		const containerW = svgWidth;

		// Position left edge at handle X; CSS margin handles the visual offset
		let minLeft = minHandleX;
		let maxLeft = maxHandleX;

		// Ensure they don't overlap
		const minDist = labelWidth + labelGap;
		if (maxLeft - minLeft < minDist) {
			const mid = (minLeft + maxLeft) / 2;
			minLeft = mid - minDist / 2;
			maxLeft = mid + minDist / 2;
		}

		// Shift pair into bounds
		if (minLeft < 0) {
			const shift = -minLeft;
			minLeft += shift;
			maxLeft += shift;
		}
		if (maxLeft > containerW - labelWidth) {
			const shift = maxLeft - (containerW - labelWidth);
			maxLeft -= shift;
			minLeft -= shift;
		}

		// Final safety clamp
		minLeft = Math.max(0, minLeft);
		maxLeft = Math.min(containerW - labelWidth, maxLeft);

		return { minLeft, maxLeft };
	});

	// ── Layout ────────────────────────────────────────────────────────

	let columnWidth = $state(288);
</script>

{#snippet histSvg()}
	{#if hasValidData}
		<svg
			width="100%"
			height={svgHeight}
			role="img"
			aria-label="Histogram for {label}"
			class="bg-zinc-950"
			bind:clientWidth={svgWidth}
		>
			<defs>
				<linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
					{#each colors as stop, i (i)}
						<stop offset="{colors.length === 1 ? 100 : (i / (colors.length - 1)) * 100}%" stop-color={stop} />
					{/each}
				</linearGradient>
			</defs>

			{#if bgPoints}
				<polyline points={bgPoints} fill="none" stroke="#3f3f46" stroke-width="1" class="non-scaling" />
			{/if}
			{#if fgPolygon}
				<polygon points={fgPolygon} fill="url(#{gradientId})" fill-opacity="0.15" stroke="none" />
			{/if}
			{#if fgPoints}
				<polyline points={fgPoints} fill="none" stroke="url(#{gradientId})" stroke-width="1.5" class="non-scaling" />
			{/if}

			<!-- Min handle -->
			<line
				x1={minHandleX}
				y1="0"
				x2={minHandleX}
				y2={svgHeight}
				stroke="#10b981"
				stroke-width="1"
				stroke-opacity="0.9"
				pointer-events="none"
			/>
			<line
				x1={minHandleX}
				y1="0"
				x2={minHandleX}
				y2={svgHeight}
				stroke="transparent"
				stroke-width="12"
				class="cursor-ew-resize"
				onpointerdown={(e) => onHandleDown(e, 'min')}
				onpointermove={onHandleMove}
				onpointerup={onHandleUp}
				role="slider"
				tabindex="0"
				aria-label="Minimum level"
				aria-valuenow={minIntensity}
			/>

			<!-- Max handle -->
			<line
				x1={maxHandleX}
				y1="0"
				x2={maxHandleX}
				y2={svgHeight}
				stroke="#f59e0b"
				stroke-width="1"
				stroke-opacity="0.9"
				pointer-events="none"
			/>
			<line
				x1={maxHandleX}
				y1="0"
				x2={maxHandleX}
				y2={svgHeight}
				stroke="transparent"
				stroke-width="12"
				class="cursor-ew-resize"
				onpointerdown={(e) => onHandleDown(e, 'max')}
				onpointermove={onHandleMove}
				onpointerup={onHandleUp}
				role="slider"
				tabindex="0"
				aria-label="Maximum level"
				aria-valuenow={maxIntensity}
			/>

			<!-- Dimming outside range -->
			<rect x="0" y="0" width={minHandleX} height={svgHeight} fill="black" opacity="0.4" pointer-events="none" />
			<rect x={maxHandleX} y="0" width={svgWidth - maxHandleX} height={svgHeight} fill="black" opacity="0.4" pointer-events="none" />
		</svg>
	{:else}
		<div class="flex items-center justify-center" style:height="{svgHeight}px">
			<span class="text-[0.65rem] text-muted-foreground">No histogram data</span>
		</div>
	{/if}
{/snippet}

<div
	class="flex flex-col transition-opacity"
	class:opacity-40={visible === false}
	bind:clientWidth={columnWidth}
	style:--label-width="{labelWidth}px"
>
	<!-- Floating Level Inputs -->
	<div class="floating-row relative" class:invisible={!hasValidData}>
		<input
			type="text"
			class="hist-input floating-input"
			style:left="{labelPositions.minLeft}px"
			value={minIntensity}
			onchange={(e) => commitFloatingInput(e, 'min')}
		/>
		<input
			type="text"
			class="hist-input floating-input"
			style:left="{labelPositions.maxLeft}px"
			value={maxIntensity}
			onchange={(e) => commitFloatingInput(e, 'max')}
		/>
	</div>

	<!-- Histogram -->
	<ContextMenu.Root>
		<ContextMenu.Trigger
			class="relative border-b border-b-input bg-transparent"
			bind:ref={histContainerEl}
			ondblclick={autoLevels}
		>
			{@render histSvg()}
		</ContextMenu.Trigger>
		<ContextMenu.Portal>
			<ContextMenu.Content
				class="z-50 min-w-36 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-xl outline-none"
				side="top"
				align="start"
			>
				<ContextMenu.Item
					class="flex cursor-default items-center rounded-sm px-2 py-1.5 text-xs outline-none select-none disabled:pointer-events-none disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground"
					onSelect={autoLevels}
					disabled={!hasValidData}
				>
					Auto Levels
				</ContextMenu.Item>
				<ContextMenu.Item
					class="flex cursor-default items-center rounded-sm px-2 py-1.5 text-xs outline-none select-none disabled:pointer-events-none disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground"
					onSelect={autoFit}
					disabled={!hasValidData}
				>
					Auto Fit
				</ContextMenu.Item>
				<ContextMenu.Separator class="my-1 h-px bg-border" />
				<ContextMenu.Item
					class="flex cursor-default items-center rounded-sm px-2 py-1.5 text-xs outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground"
					onSelect={() => {
						windowMin = 0;
						windowMax = dataTypeMax;
					}}
				>
					Reset Window
				</ContextMenu.Item>
				{#if onVisibilityChange}
					<ContextMenu.Separator class="my-1 h-px bg-border" />
					<ContextMenu.Item
						class="flex cursor-default items-center rounded-sm px-2 py-1.5 text-xs outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground"
						onSelect={() => onVisibilityChange?.(!visible)}
					>
						{visible ? 'Hide' : 'Show'} Channel
					</ContextMenu.Item>
				{/if}
			</ContextMenu.Content>
		</ContextMenu.Portal>
	</ContextMenu.Root>

	<!-- Window Range + Label -->
	<div class="flex -translate-y-px items-center justify-between">
		<input type="text" class="hist-input" value={windowMin} onchange={(e) => commitWindowInput(e, 'min')} />

		<div class="flex items-center gap-1">
			{#if onVisibilityChange}
				<button
					onclick={() => onVisibilityChange?.(!visible)}
					class="flex items-center rounded"
					style="color: {colors[colors.length - 1]};"
					aria-label={visible ? 'Hide channel' : 'Show channel'}
				>
					<Icon icon={visible ? 'mdi:eye' : 'mdi:eye-off'} width="12" height="12" />
				</button>
			{/if}
			<ColormapPicker
				{label}
				{colormap}
				{catalog}
				{onColormapChange}
				width={columnWidth}
				align="center"
				triggerClass="cursor-pointer text-[0.65rem] leading-none font-medium transition-colors hover:brightness-125"
			/>
		</div>

		<input
			type="text"
			class="hist-input hist-input-right"
			value={windowMax}
			onchange={(e) => commitWindowInput(e, 'max')}
		/>
	</div>
</div>

<style>
	.non-scaling {
		vector-effect: non-scaling-stroke;
	}

	.floating-row {
		height: 14px;
		overflow: visible;
	}

	.hist-input {
		--char-offset: 3px;
		width: var(--label-width, 36px);
		margin-left: calc(-1 * var(--char-offset));
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.6rem;
		line-height: 1;
		color: var(--color-muted-foreground);
		background: transparent;
		border: 1px solid transparent;
		border-radius: 2px;
		outline: none;
		padding: 0;
		user-select: none;
		transition: border-color 0.15s ease;
	}

	.hist-input-right {
		margin-left: 0;
		margin-right: calc(-1 * var(--char-offset));
		text-align: right;
	}

	.hist-input:hover {
		border-color: var(--color-input);
	}

	.hist-input:focus {
		color: var(--color-foreground);
		border-color: var(--color-ring);
	}

	.floating-input {
		position: absolute;
		bottom: 0;
	}
</style>
