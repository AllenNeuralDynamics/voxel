<script lang="ts">
	import LegacySpinBox from '$lib/ui/primitives/LegacySpinBox.svelte';
	import { computeAutoLevels } from '$lib/preview/utils';

	interface Props {
		histData: number[] | undefined | null;
		levelsMin?: number;
		levelsMax?: number;
		onLevelsChange?: (min: number, max: number) => void;
		dataTypeMax?: number;
		colors?: string[];
	}

	let {
		histData: histogram,
		levelsMin = 0.0,
		levelsMax = 1.0,
		onLevelsChange,
		dataTypeMax = 65535,
		colors = ['#06b6d4']
	}: Props = $props();

	const gradientId = `hist-grad-${crypto.randomUUID().slice(0, 8)}`;

	let displayWindowMin = $state(0);
	let displayWindowMax = $state(0);
	let hasAutoFit = $state(false);
	let prevDataTypeMax = 0;

	$effect.pre(() => {
		if (dataTypeMax !== prevDataTypeMax) {
			displayWindowMax = dataTypeMax;
			displayWindowMin = 0;
			hasAutoFit = false;
			prevDataTypeMax = dataTypeMax;
		}
	});

	const hasValidData = $derived(!!histogram && histogram.length > 0);

	const ghostButtonClass =
		'min-w-14 justify-self-center rounded-sm px-1.5 py-[0.25] text-[0.6rem] text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300 disabled:cursor-not-allowed disabled:opacity-0';

	let width = $state(256);
	const height = 32;

	const visibleBins = $derived(() => {
		if (!histogram || histogram.length === 0) return { startBin: 0, endBin: 0 };
		const numBins = histogram.length;
		const startBin = Math.floor((displayWindowMin / dataTypeMax) * (numBins - 1));
		const endBin = Math.ceil((displayWindowMax / dataTypeMax) * (numBins - 1));
		return { startBin, endBin };
	});

	const displayHistogram = $derived(() => {
		if (!hasValidData || !histogram) return [];

		const { startBin, endBin } = visibleBins();
		const windowedHistogram = histogram.slice(startBin, endBin + 1);
		const maxCount = Math.max(...windowedHistogram);

		if (maxCount === 0) return windowedHistogram.map(() => 0);
		return windowedHistogram.map((count) => count / maxCount);
	});

	const numBins = $derived(histogram?.length || 1);
	const minBin = $derived(Math.round(levelsMin * (numBins - 1)));
	const maxBin = $derived(Math.round(levelsMax * (numBins - 1)));
	const minIntensity = $derived(Math.round(levelsMin * dataTypeMax));
	const maxIntensity = $derived(Math.round(levelsMax * dataTypeMax));

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

		const { startBin, endBin } = visibleBins();
		const relativePosition = x / width;
		const binInWindow = relativePosition * (endBin - startBin);
		const absoluteBin = startBin + binInWindow;
		const level = absoluteBin / (numBins - 1);

		if (isDraggingMin && onLevelsChange) {
			const newMin = Math.min(level, levelsMax - 0.01);
			onLevelsChange(Math.max(0, newMin), levelsMax);
		} else if (isDraggingMax && onLevelsChange) {
			const newMax = Math.max(level, levelsMin + 0.01);
			onLevelsChange(levelsMin, Math.min(1, newMax));
		}
	}

	$effect(() => {
		const minIntensityValue = Math.round(levelsMin * dataTypeMax);
		const maxIntensityValue = Math.round(levelsMax * dataTypeMax);

		if (minIntensityValue < displayWindowMin) {
			displayWindowMin = Math.max(0, minIntensityValue);
		}
		if (maxIntensityValue > displayWindowMax) {
			displayWindowMax = Math.min(dataTypeMax, maxIntensityValue);
		}
	});

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

	function handleFitDisplayWindow() {
		if (!hasValidData || !histogram) return;

		let minBin = 0;
		let maxBin = numBins - 1;

		for (let i = 0; i < numBins; i++) {
			if (histogram[i] > 0) {
				minBin = i;
				break;
			}
		}
		for (let i = numBins - 1; i >= 0; i--) {
			if (histogram[i] > 0) {
				maxBin = i;
				break;
			}
		}

		const range = maxBin - minBin;
		const padding = range * 0.15;
		const paddedMinBin = Math.max(0, minBin - padding);
		const paddedMaxBin = Math.min(numBins - 1, maxBin + padding);

		displayWindowMin = Math.round((paddedMinBin / (numBins - 1)) * dataTypeMax);
		displayWindowMax = Math.round((paddedMaxBin / (numBins - 1)) * dataTypeMax);
		hasAutoFit = true;
	}

	$effect(() => {
		if (hasValidData && !hasAutoFit && onLevelsChange) {
			handleFitDisplayWindow();
		}
	});

	const minHandlePos = $derived(() => {
		const { startBin, endBin } = visibleBins();
		if (minBin < startBin) return 0;
		if (minBin > endBin) return width;
		return ((minBin - startBin) / (endBin - startBin)) * width;
	});

	const maxHandlePos = $derived(() => {
		const { startBin, endBin } = visibleBins();
		if (maxBin < startBin) return 0;
		if (maxBin > endBin) return width - 2;
		return Math.min(((maxBin - startBin) / (endBin - startBin)) * width, width - 2);
	});

	function handleAutoLevels() {
		if (!hasValidData || !histogram || !onLevelsChange) return;
		const newLevels = computeAutoLevels(histogram);
		if (newLevels) {
			onLevelsChange(newLevels.min, newLevels.max);
		}
	}
</script>

<div class="histogram-widget flex flex-col">
	<div class="flex items-center justify-between text-zinc-300">
		{#if onLevelsChange}
			<LegacySpinBox
				value={minIntensity}
				min={0}
				max={maxIntensity - 1}
				step={100}
				numCharacters={5}
				align="left"
				showButtons={false}
				onChange={(newValue) => {
					const newMin = newValue / dataTypeMax;
					onLevelsChange(newMin, levelsMax);
				}}
			/>
		{:else}
			<span class="justify-self-start">{minIntensity}</span>
		{/if}

		{#if onLevelsChange}
			<button type="button" onclick={handleAutoLevels} disabled={!hasValidData} class={ghostButtonClass}>
				auto levels
			</button>
		{/if}

		{#if onLevelsChange}
			<LegacySpinBox
				value={maxIntensity}
				min={minIntensity + 1}
				max={dataTypeMax}
				step={100}
				numCharacters={5}
				align="right"
				showButtons={false}
				onChange={(newValue) => {
					const newMax = newValue / dataTypeMax;
					onLevelsChange(levelsMin, newMax);
				}}
			/>
		{:else}
			<span class="justify-self-end">{maxIntensity}</span>
		{/if}
	</div>

	<div class="border border-zinc-600 bg-transparent">
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

			{@const foregroundFillPoints = histData
				.map((value, i) => {
					const actualBin = startBin + i;
					if (actualBin >= minBin && actualBin <= maxBin) {
						const x = (i / (histData.length - 1 || 1)) * width;
						const y = height - value * height;
						return { x, y };
					}
					return null;
				})
				.filter((p): p is { x: number; y: number } => p !== null)}

			<svg
				width="100%"
				{height}
				role="img"
				aria-label="Histogram"
				class="histogram-svg cursor-crosshair bg-zinc-950"
				onmousemove={handleMouseMove}
				bind:clientWidth={width}
			>
				<defs>
					<linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
						{#each colors as stop, i (i)}
							<stop offset="{colors.length === 1 ? 100 : (i / (colors.length - 1)) * 100}%" stop-color={stop} />
						{/each}
					</linearGradient>
				</defs>

				{#if backgroundPoints}
					<polyline points={backgroundPoints} fill="none" stroke="#3f3f46" stroke-width="1" class="histogram-line" />
				{/if}

				{#if foregroundFillPoints.length > 1}
					<polygon
						points="{foregroundFillPoints[0].x},{height} {foregroundFillPoints
							.map((p) => `${p.x},${p.y}`)
							.join(' ')} {foregroundFillPoints[foregroundFillPoints.length - 1].x},{height}"
						fill="url(#{gradientId})"
						fill-opacity="0.15"
						stroke="none"
					/>
				{/if}

				{#if foregroundPoints}
					<polyline
						points={foregroundPoints}
						fill="none"
						stroke="url(#{gradientId})"
						stroke-width="1.5"
						class="histogram-line"
					/>
				{/if}

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
				<span class="my-auto text-[0.65rem] text-zinc-600">No histogram data</span>
			</div>
		{/if}
	</div>
	<div class="flex items-center justify-between text-zinc-300">
		<LegacySpinBox
			bind:value={displayWindowMin}
			min={0}
			max={displayWindowMax - 1}
			step={100}
			placeholder="0"
			numCharacters={5}
			showButtons={false}
			align="left"
		/>
		<button type="button" onclick={handleFitDisplayWindow} disabled={!hasValidData} class={ghostButtonClass}>
			auto fit
		</button>
		<LegacySpinBox
			bind:value={displayWindowMax}
			min={displayWindowMin + 1}
			max={dataTypeMax}
			step={100}
			placeholder={dataTypeMax.toString()}
			numCharacters={5}
			showButtons={false}
			align="right"
		/>
	</div>
</div>

<style>
	.histogram-line {
		vector-effect: non-scaling-stroke;
	}
</style>
