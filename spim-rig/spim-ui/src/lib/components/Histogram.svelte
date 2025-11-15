<script lang="ts">
	import DraggableNumberInput from './DraggableNumberInput.svelte';

	interface Props {
		histData: number[] | undefined | null; // Allow null/undefined
		levelsMin?: number;
		levelsMax?: number;
		onLevelsChange?: (min: number, max: number) => void;
		dataTypeMax?: number; // Maximum value of the data type (e.g., 65535 for uint16)
		color?: string; // Color for histogram bars and display range text
	}

	let {
		histData: histogram,
		levelsMin = 0.0,
		levelsMax = 1.0,
		onLevelsChange,
		dataTypeMax = 65535,
		color = '#06b6d4'
	}: Props = $props();

	// Display window (what range of intensities to show in the histogram)
	let displayWindowMin = $state(0);
	let displayWindowMax = $state(dataTypeMax);

	// --- NEW: Check for valid data ---
	// Support variable-length histograms (256 for uint8, 65536 for uint16, etc.)
	const hasValidData = $derived(!!histogram && histogram.length > 0);

	// SVG dimensions
	let width = $state(256); // Default, will be updated by bind:clientWidth
	const height = 48;

	// Calculate which bins fall within the display window
	const visibleBins = $derived(() => {
		if (!histogram || histogram.length === 0) return { startBin: 0, endBin: 0 };
		const numBins = histogram.length;
		const startBin = Math.floor((displayWindowMin / dataTypeMax) * (numBins - 1));
		const endBin = Math.ceil((displayWindowMax / dataTypeMax) * (numBins - 1));
		return { startBin, endBin };
	});

	// Get windowed and normalized histogram data that stretches to fill display
	const displayHistogram = $derived(() => {
		// Use hasValidData check
		if (!hasValidData || !histogram) return [];

		const { startBin, endBin } = visibleBins();
		const windowedHistogram = histogram.slice(startBin, endBin + 1);
		const maxCount = Math.max(...windowedHistogram);

		if (maxCount === 0) return windowedHistogram.map(() => 0);

		// Debug: log histogram stats
		const totalPixels = histogram.reduce((sum, count) => sum + count, 0);
		const nonZeroBins = histogram.filter((count) => count > 0).length;
		console.log('[Histogram Debug]', {
			totalPixels,
			nonZeroBins,
			maxCount,
			minValue: histogram.findIndex((count) => count > 0),
			maxValue: 255 - [...histogram].reverse().findIndex((count) => count > 0),
			displayWindow: { min: displayWindowMin, max: displayWindowMax },
			visibleBins: { startBin, endBin, count: windowedHistogram.length }
		});

		// Return only the windowed bins, normalized
		return windowedHistogram.map((count) => count / maxCount);
	});

	// Convert levels (0-1) to bin indices and to actual intensity values
	// Bin indices now match dataTypeMax (e.g., 0-65535 for uint16)
	const numBins = $derived(histogram?.length || 1);
	const minBin = $derived(Math.round(levelsMin * (numBins - 1)));
	const maxBin = $derived(Math.round(levelsMax * (numBins - 1)));
	const minIntensity = $derived(Math.round(levelsMin * dataTypeMax));
	const maxIntensity = $derived(Math.round(levelsMax * dataTypeMax));

	// Dragging state
	let isDraggingMin = $state(false);
	let isDraggingMax = $state(false);

	function handleMouseDown(e: MouseEvent, handle: 'min' | 'max') {
		e.preventDefault();
		if (handle === 'min') {
			isDraggingMin = true;
		} else {
			isDraggingMax = true;
		}
	}

	function handleMouseMove(e: MouseEvent) {
		if (!isDraggingMin && !isDraggingMax) return;

		const svg = e.currentTarget as SVGSVGElement;
		const rect = svg.getBoundingClientRect();
		const x = Math.max(0, Math.min(width, e.clientX - rect.left));

		// Convert x position to bin index within the display window
		const { startBin, endBin } = visibleBins();
		const relativePosition = x / width; // 0 to 1 within display
		const binInWindow = relativePosition * (endBin - startBin);
		const absoluteBin = startBin + binInWindow;
		const level = absoluteBin / (numBins - 1); // Normalize to 0-1

		if (isDraggingMin && onLevelsChange) {
			// Ensure min doesn't exceed max
			const newMin = Math.min(level, levelsMax - 0.01);
			onLevelsChange(Math.max(0, newMin), levelsMax);
		} else if (isDraggingMax && onLevelsChange) {
			// Ensure max doesn't go below min
			const newMax = Math.max(level, levelsMin + 0.01);
			onLevelsChange(levelsMin, Math.min(1, newMax));
		}
	}

	function handleMouseUp() {
		isDraggingMin = false;
		isDraggingMax = false;
	}

	$effect(() => {
		if (isDraggingMin || isDraggingMax) {
			document.addEventListener('mouseup', handleMouseUp);
			return () => {
				document.removeEventListener('mouseup', handleMouseUp);
			};
		}
	});

	function handleAutoLevels() {
		// Use hasValidData check
		if (!hasValidData || !histogram || !onLevelsChange) return;

		// Find 1st and 99th percentile
		const totalPixels = histogram.reduce((sum, count) => sum + count, 0);
		const p1Threshold = totalPixels * 0.01;
		const p99Threshold = totalPixels * 0.99;

		let cumulative = 0;
		let minBin = 0;
		let maxBin = numBins - 1;

		// Find min (1st percentile)
		for (let i = 0; i < numBins; i++) {
			cumulative += histogram[i];
			if (cumulative >= p1Threshold) {
				minBin = i;
				break;
			}
		}

		// Find max (99th percentile)
		cumulative = 0;
		for (let i = 0; i < numBins; i++) {
			cumulative += histogram[i];
			if (cumulative >= p99Threshold) {
				maxBin = i;
				break;
			}
		}

		onLevelsChange(minBin / (numBins - 1), maxBin / (numBins - 1));
	}

	// function resetDisplayWindow() {
	// 	displayWindowMin = 0;
	// 	displayWindowMax = dataTypeMax;
	// }

	// Calculate handle positions (clamped to display window edges if outside)
	const minHandlePos = $derived(() => {
		const { startBin, endBin } = visibleBins();
		if (minBin < startBin) return 0;
		if (minBin > endBin) return width;
		const pos = ((minBin - startBin) / (endBin - startBin)) * width;
		console.log('[Handle Debug] Min:', { minBin, startBin, endBin, pos, levelsMin });
		return pos;
	});

	const maxHandlePos = $derived(() => {
		const { startBin, endBin } = visibleBins();
		if (maxBin < startBin) return 0;
		if (maxBin > endBin) return width - 2; // Inset by 2px so it's visible
		const pos = ((maxBin - startBin) / (endBin - startBin)) * width;
		// Clamp to ensure it's always visible (2px from edge)
		const clampedPos = Math.min(pos, width - 2);
		// console.log('[Handle Debug] Max:', { maxBin, startBin, endBin, pos, clampedPos, levelsMax, width });
		return clampedPos;
	});
</script>

<div class="histogram-widget flex flex-col">
	<div class="flex items-center justify-between text-zinc-400">
		{#if onLevelsChange}
			<DraggableNumberInput
				value={minIntensity}
				min={0}
				max={maxIntensity - 1}
				step={1}
				numCharacters={5}
				align="left"
				onValueChange={(newValue) => {
					const newMin = newValue / dataTypeMax;
					onLevelsChange(newMin, levelsMax);
				}}
			/>
		{:else}
			<span class="justify-self-start">{minIntensity}</span>
		{/if}

		{#if onLevelsChange}
			<button
				type="button"
				onclick={handleAutoLevels}
				disabled={!hasValidData}
				class="justify-self-center rounded-sm px-1.5 py-[0.25] text-[0.5rem] text-zinc-600 transition-colors hover:bg-zinc-800 hover:text-zinc-400"
			>
				auto levels
			</button>
		{/if}

		{#if onLevelsChange}
			<DraggableNumberInput
				value={maxIntensity}
				min={minIntensity + 1}
				max={dataTypeMax}
				step={1}
				numCharacters={5}
				align="right"
				onValueChange={(newValue) => {
					const newMax = newValue / dataTypeMax;
					onLevelsChange(levelsMin, newMax);
				}}
			/>
		{:else}
			<span class="justify-self-end">{maxIntensity}</span>
		{/if}
	</div>

	<div class="border border-zinc-800/50 bg-transparent">
		{#if hasValidData}
			{@const histData = displayHistogram()}
			{@const { startBin } = visibleBins()}
			{@const backgroundPoints = histData
				.map((value, i) => {
					const x = (i / (histData.length - 1 || 1)) * width;
					const y = height - value * height;
					return `${x},${y}`;
				})
				.join(' ')}
			{@const foregroundPoints = histData
				.map((value, i) => {
					const actualBin = startBin + i;
					if (actualBin >= minBin && actualBin <= maxBin) {
						const x = (i / (histData.length - 1 || 1)) * width;
						const y = height - value * height;
						return `${x},${y}`;
					}
					return null;
				})
				.filter((p) => p !== null)
				.join(' ')}

			<svg
				width="100%"
				{height}
				role="img"
				aria-label="Histogram"
				class="histogram-svg cursor-crosshair bg-zinc-950"
				onmousemove={handleMouseMove}
				bind:clientWidth={width}
			>
				<!-- Background line (full histogram) -->
				{#if backgroundPoints}
					<polyline points={backgroundPoints} fill="none" stroke="#3f3f46" stroke-width="1" class="histogram-line" />
				{/if}

				<!-- Foreground line (within levels range) -->
				{#if foregroundPoints}
					<polyline points={foregroundPoints} fill="none" stroke={color} stroke-width="1.5" class="histogram-line" />
				{/if}

				<!-- Min handle: visible line -->
				<line
					x1={minHandlePos()}
					y1="0"
					x2={minHandlePos()}
					y2={height}
					stroke="#10b981"
					stroke-width="1.5"
					stroke-opacity="0.9"
					pointer-events="none"
				/>
				<!-- Min handle: wider invisible touch target -->
				<line
					role="slider"
					tabindex="0"
					aria-label="Minimum level"
					aria-valuenow={levelsMin}
					x1={minHandlePos()}
					y1="0"
					x2={minHandlePos()}
					y2={height}
					stroke="transparent"
					stroke-width="12"
					class="cursor-ew-resize"
					onmousedown={(e) => handleMouseDown(e, 'min')}
				/>

				<!-- Max handle: visible line -->
				<line
					x1={maxHandlePos()}
					y1="0"
					x2={maxHandlePos()}
					y2={height}
					stroke="#f59e0b"
					stroke-width="1.5"
					stroke-opacity="0.9"
					pointer-events="none"
				/>
				<!-- Max handle: wider invisible touch target -->
				<line
					role="slider"
					tabindex="0"
					aria-label="Maximum level"
					aria-valuenow={levelsMax}
					x1={maxHandlePos()}
					y1="0"
					x2={maxHandlePos()}
					y2={height}
					stroke="transparent"
					stroke-width="12"
					class="cursor-ew-resize"
					onmousedown={(e) => handleMouseDown(e, 'max')}
				/>

				<rect x="0" y="0" width={minHandlePos()} {height} fill="black" opacity="0.4" pointer-events="none" />
				<rect
					x={maxHandlePos()}
					y="0"
					width={width - maxHandlePos()}
					{height}
					fill="black"
					opacity="0.4"
					pointer-events="none"
				/>
			</svg>
		{:else}
			<div class="flex items-center justify-center" style="height: {height}px;">
				<span class="my-auto text-[0.65rem] text-zinc-700">No histogram data</span>
			</div>
		{/if}
	</div>
	<div class="flex items-center justify-between text-zinc-400">
		<DraggableNumberInput
			bind:value={displayWindowMin}
			min={0}
			max={displayWindowMax - 1}
			step={100}
			placeholder="0"
			numCharacters={5}
			align="left"
		/>
		<DraggableNumberInput
			bind:value={displayWindowMax}
			min={displayWindowMin + 1}
			max={dataTypeMax}
			step={100}
			placeholder={dataTypeMax.toString()}
			numCharacters={5}
			align="right"
		/>
	</div>
</div>

<style>
	.histogram-line {
		vector-effect: non-scaling-stroke;
	}
</style>
