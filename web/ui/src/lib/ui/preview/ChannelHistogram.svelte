<script lang="ts">
	import { SpinBox } from '$lib/ui/primitives';
	import { computeAutoLevels } from '$lib/utils';
	import ColormapPicker from './ColormapPicker.svelte';
	import type { ColormapCatalog } from '$lib/main';

	type WindowMode = 'visible' | 'hover' | 'inline';

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
		windowMode?: WindowMode;
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
		windowMode = 'hover'
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

	// Expand display window if levels are dragged outside it
	$effect(() => {
		if (minIntensity < windowMin) windowMin = Math.max(0, minIntensity);
		if (maxIntensity > windowMax) windowMax = Math.min(dataTypeMax, maxIntensity);
	});

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

	function onHandleDown(e: MouseEvent, handle: 'min' | 'max') {
		e.preventDefault();
		dragging = handle;
	}

	function onSvgMouseMove(e: MouseEvent) {
		if (!dragging) return;
		const svg = e.currentTarget as SVGSVGElement;
		const rect = svg.getBoundingClientRect();
		const x = Math.max(0, Math.min(svgWidth, e.clientX - rect.left));
		const rel = x / svgWidth;
		const bin = startBin + rel * (endBin - startBin);
		const level = bin / (numBins - 1);

		if (dragging === 'min') {
			onLevelsChange(Math.max(0, Math.min(level, levelsMax - 0.01)), levelsMax);
		} else {
			onLevelsChange(levelsMin, Math.min(1, Math.max(level, levelsMin + 0.01)));
		}
	}

	function onMouseUp() {
		dragging = null;
	}

	$effect(() => {
		if (dragging) {
			document.addEventListener('mouseup', onMouseUp);
			return () => document.removeEventListener('mouseup', onMouseUp);
		}
	});

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

	// ── Scroll-to-Zoom (inline mode) ─────────────────────────────────

	let histContainerEl = $state<HTMLDivElement | undefined>();

	function onHistWheel(e: WheelEvent) {
		if (windowMode !== 'inline') return;
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
		if (!histContainerEl || windowMode !== 'inline') return;
		histContainerEl.addEventListener('wheel', onHistWheel, { passive: false });
		return () => histContainerEl?.removeEventListener('wheel', onHistWheel);
	});

	// ── Layout ────────────────────────────────────────────────────────

	let columnWidth = $state(288);

	const ghostBtnClass =
		'min-w-14 rounded-sm px-1.5 py-px text-[0.6rem] text-zinc-400 ' +
		'transition-colors hover:bg-zinc-800 hover:text-zinc-300 ' +
		'disabled:cursor-not-allowed disabled:opacity-0';
</script>

<div class="channel-histogram flex flex-col" bind:clientWidth={columnWidth}>
	<!-- Window Range -->
	{#if windowMode !== 'inline'}
		<div
			class="flex items-center justify-between text-zinc-400"
			class:window-row-hover={windowMode === 'hover'}
		>
			<SpinBox
				bind:value={windowMin}
				min={0}
				max={windowMax - 1}
				step={100}
				numCharacters={5}
				align="left"
				showButtons={false}
				size="xs"
			/>
			<button type="button" onclick={autoFit} disabled={!hasValidData} class={ghostBtnClass}>auto fit</button>
			<SpinBox
				bind:value={windowMax}
				min={windowMin + 1}
				max={dataTypeMax}
				step={100}
				numCharacters={5}
				align="right"
				showButtons={false}
				size="xs"
			/>
		</div>
	{/if}

	<!-- Histogram -->
	<div class="border border-zinc-600 bg-transparent" bind:this={histContainerEl}>
		{#if hasValidData}
			<svg
				width="100%"
				height={svgHeight}
				role="img"
				aria-label="Histogram for {label}"
				class="cursor-crosshair bg-zinc-950"
				onmousemove={onSvgMouseMove}
				ondblclick={autoLevels}
				oncontextmenu={(e) => {
					if (windowMode === 'inline') {
						e.preventDefault();
						autoFit();
					}
				}}
				bind:clientWidth={svgWidth}
			>
				<defs>
					<linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
						{#each colors as stop, i (i)}
							<stop
								offset="{colors.length === 1 ? 100 : (i / (colors.length - 1)) * 100}%"
								stop-color={stop}
							/>
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
					<polyline
						points={fgPoints}
						fill="none"
						stroke="url(#{gradientId})"
						stroke-width="1.5"
						class="non-scaling"
					/>
				{/if}

				<!-- Min handle -->
				<line
					x1={minHandleX} y1="0" x2={minHandleX} y2={svgHeight}
					stroke="#10b981" stroke-width="1.5" stroke-opacity="0.9" pointer-events="none"
				/>
				<line
					x1={minHandleX} y1="0" x2={minHandleX} y2={svgHeight}
					stroke="transparent" stroke-width="12" class="cursor-ew-resize"
					onmousedown={(e) => onHandleDown(e, 'min')}
					role="slider" tabindex="0" aria-label="Minimum level" aria-valuenow={levelsMin}
				/>

				<!-- Max handle -->
				<line
					x1={maxHandleX} y1="0" x2={maxHandleX} y2={svgHeight}
					stroke="#f59e0b" stroke-width="1.5" stroke-opacity="0.9" pointer-events="none"
				/>
				<line
					x1={maxHandleX} y1="0" x2={maxHandleX} y2={svgHeight}
					stroke="transparent" stroke-width="12" class="cursor-ew-resize"
					onmousedown={(e) => onHandleDown(e, 'max')}
					role="slider" tabindex="0" aria-label="Maximum level" aria-valuenow={levelsMax}
				/>

				<!-- Dimming outside range -->
				<rect x="0" y="0" width={minHandleX} height={svgHeight} fill="black" opacity="0.4" pointer-events="none" />
				<rect
					x={maxHandleX} y="0" width={svgWidth - maxHandleX} height={svgHeight}
					fill="black" opacity="0.4" pointer-events="none"
				/>
			</svg>
		{:else}
			<div class="flex items-center justify-center" style:height="{svgHeight}px">
				<span class="text-[0.65rem] text-zinc-600">No histogram data</span>
			</div>
		{/if}
	</div>

	<!-- Levels + Label -->
	<div class="flex items-center justify-between text-zinc-400">
		<SpinBox
			value={minIntensity}
			min={0}
			max={maxIntensity - 1}
			step={100}
			numCharacters={5}
			align="left"
			showButtons={false}
			size="xs"
			onChange={(v) => onLevelsChange(v / dataTypeMax, levelsMax)}
		/>

		<ColormapPicker
			{label}
			{colormap}
			{catalog}
			{onColormapChange}
			width={columnWidth}
			align="center"
			triggerClass="cursor-pointer text-[0.65rem] leading-none font-medium transition-colors hover:brightness-125"
		/>

		<SpinBox
			value={maxIntensity}
			min={minIntensity + 1}
			max={dataTypeMax}
			step={100}
			numCharacters={5}
			align="right"
			showButtons={false}
			size="xs"
			onChange={(v) => onLevelsChange(levelsMin, v / dataTypeMax)}
		/>
	</div>
</div>

<style>
	.non-scaling {
		vector-effect: non-scaling-stroke;
	}

	.window-row-hover {
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.15s ease;
	}

	.channel-histogram:hover .window-row-hover,
	.channel-histogram:focus-within .window-row-hover {
		opacity: 1;
		pointer-events: auto;
	}
</style>
