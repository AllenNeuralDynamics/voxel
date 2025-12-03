<script lang="ts">
	import uPlot from 'uplot';
	import type { RigManager } from '$lib/core';
	import { onDestroy } from 'svelte';
	import ProfileDevicesToggle from '$lib/ProfileDevicesToggle.svelte';
	import SpinBox from '$lib/ui/SpinBox.svelte';
	import 'uplot/dist/uPlot.min.css';

	interface Props {
		manager: RigManager;
	}

	let { manager }: Props = $props();

	// Internal state for visible devices
	let visibleDevices = $state(new Set<string>());

	let plotContainer = $state<HTMLDivElement>();
	let chart: uPlot | undefined;
	let containerHeight = $state(400);

	// Get active profile and waveforms
	const activeProfile = $derived(manager.activeProfile);
	const waveforms = $derived(activeProfile?.waveforms);
	const timing = $derived(activeProfile?.daq?.timing);

	let numCycles = $state(2);

	const timeData = $derived.by(() => {
		if (!timing || !waveforms) return [];

		const firstWaveform = Object.values(waveforms)[0];
		if (!firstWaveform) return [];

		const actualDataLength = firstWaveform.length;
		const duration = Number(timing.duration);
		const restTime = Number(timing.rest_time || 0);

		// Single cycle duration - DON'T multiply by numCycles here
		const totalDuration = duration + restTime;

		const timeStep = (totalDuration * 1000) / actualDataLength;
		return Array.from({ length: actualDataLength }, (_, i) => i * timeStep);
	});

	const plotData = $derived.by(() => {
		if (!waveforms || !timeData.length) return [[]];

		const visibleWaveforms = Object.entries(waveforms).filter(([deviceId]) => visibleDevices.has(deviceId));
		if (visibleWaveforms.length === 0) return [timeData];

		// Repeat time data for all cycles
		const duration = Number(timing?.duration || 0);
		const restTime = Number(timing?.rest_time || 0);
		const cycleDuration = (duration + restTime) * 1000; // ms per cycle

		const repeatedTimeData = Array.from({ length: timeData.length * numCycles }, (_, i) => {
			const cycle = Math.floor(i / timeData.length);
			const indexInCycle = i % timeData.length;
			return timeData[indexInCycle] + cycle * cycleDuration;
		});

		const data: (number[] | null[])[] = [repeatedTimeData];

		visibleWaveforms.forEach(([, voltages]) => {
			const allCyclesData = Array(numCycles).fill(voltages).flat();
			data.push(allCyclesData);
		});

		return data;
	});

	// Format timing values for display
	const formatFrequency = (hz: number) => {
		if (hz >= 1000000) return `${(hz / 1000000).toFixed(2)} MHz`;
		if (hz >= 1000) return `${(hz / 1000).toFixed(2)} kHz`;
		return `${hz.toFixed(2)} Hz`;
	};

	const formatTime = (seconds: number) => {
		if (seconds >= 1) return `${seconds.toFixed(3)} s`;
		if (seconds >= 0.001) return `${(seconds * 1000).toFixed(2)} ms`;
		return `${(seconds * 1000000).toFixed(2)} μs`;
	};

	// Define color palette for devices
	const opacity = 0.5;
	const colorPalette = [
		`rgba(16, 185, 129, ${opacity})`, // emerald
		`rgba(59, 130, 246, ${opacity})`, // blue
		`rgba(245, 158, 11, ${opacity})`, // amber
		`rgba(239, 68, 68, ${opacity})`, // red
		`rgba(139, 92, 246, ${opacity})`, // violet
		`rgba(236, 72, 153, ${opacity})`, // pink
		`rgba(6, 182, 212, ${opacity})`, // cyan
		`rgba(132, 204, 22, ${opacity})`, // lime
		`rgba(249, 115, 22, ${opacity})`, // orange
		`rgba(99, 102, 241, ${opacity})` // indigo
	];

	// Build color map for all devices (for legend in tree selector)
	const deviceColors = $derived.by(() => {
		if (!waveforms) return {};

		const colorMap: Record<string, string> = {};
		Object.keys(waveforms).forEach((deviceId, idx) => {
			colorMap[deviceId] = colorPalette[idx % colorPalette.length];
		});
		return colorMap;
	});

	// Build series configuration
	const series = $derived.by(() => {
		if (!waveforms) return [{ label: 'Time (ms)' }];

		const visibleDeviceIds = Object.keys(waveforms).filter((deviceId) => visibleDevices.has(deviceId));

		return [
			{ label: 'Time (ms)' },
			...visibleDeviceIds.map((deviceId) => ({
				label: deviceId,
				stroke: deviceColors[deviceId],
				width: 1.5,
				points: { show: false },
				dash: [5, 10]
			}))
		];
	});

	// Create or update chart
	$effect(() => {
		if (!plotContainer) return;

		const hasData = plotData.length > 1 && plotData[0].length > 0;

		// If no data, destroy chart if it exists
		if (!hasData) {
			if (chart) {
				chart.destroy();
				chart = undefined;
			}
			return;
		}

		// If chart exists and series hasn't changed, just update data
		if (chart && chart.series.length === series.length) {
			chart.setData(plotData as uPlot.AlignedData);
			return;
		}

		// Otherwise, recreate the chart (series changed or first creation)
		if (chart) {
			chart.destroy();
			chart = undefined;
		}

		containerHeight = plotContainer.clientHeight || 400;
		const opts: uPlot.Options = {
			width: plotContainer.clientWidth,
			height: containerHeight,
			series: series,
			axes: [
				{
					label: 'Time (ms)',
					labelFont: '12px system-ui, -apple-system, sans-serif',
					font: '11px system-ui, -apple-system, sans-serif',
					stroke: '#71717a',
					grid: { stroke: '#3f3f46', width: 1 }
				},
				{
					label: 'Voltage (V)',
					labelFont: '12px system-ui, -apple-system, sans-serif',
					font: '11px system-ui, -apple-system, sans-serif',
					stroke: '#71717a',
					grid: { stroke: '#3f3f46', width: 1 }
				}
			],
			scales: {
				x: {
					time: false
				}
			},
			legend: {
				show: false
			},
			cursor: {
				drag: {
					x: true,
					y: false
				}
			},
			focus: {
				alpha: 0.3
			}
		};

		chart = new uPlot(opts, plotData as uPlot.AlignedData, plotContainer);
	});

	// Use ResizeObserver to handle both window and pane resizing
	let resizeObserver: ResizeObserver | undefined;

	$effect(() => {
		if (!plotContainer) return;

		// Create ResizeObserver to watch for container size changes
		resizeObserver = new ResizeObserver(() => {
			if (chart && plotContainer) {
				containerHeight = plotContainer.clientHeight || 400;
				chart.setSize({
					width: plotContainer.clientWidth,
					height: containerHeight
				});
			}
		});

		resizeObserver.observe(plotContainer);

		return () => {
			resizeObserver?.disconnect();
		};
	});

	onDestroy(() => {
		resizeObserver?.disconnect();
		if (chart) {
			chart.destroy();
		}
	});
</script>

<div class="flex h-full px-4">
	<div class="flex flex-1 flex-col p-4">
		{#if !waveforms}
			<div class="flex h-full items-center justify-center">
				<p class="text-xs text-zinc-500">No waveform data available</p>
			</div>
		{:else if Object.keys(waveforms).filter((id) => visibleDevices.has(id)).length === 0}
			<div class="flex h-full items-center justify-center">
				<p class="text-xs text-zinc-500">Select devices to view waveforms</p>
			</div>
		{:else}
			<div bind:this={plotContainer} class="h-full w-full"></div>
		{/if}
	</div>
	<div class="flex flex-col gap-6 py-8">
		{#if timing}
			<div class="rounded border border-zinc-700 bg-zinc-800/50 p-3">
				<h3 class="mb-2 text-xs font-medium text-zinc-300">Acquisition Timing</h3>
				<div class="space-y-1.5 text-[0.65rem] text-zinc-400">
					<div class="flex justify-between">
						<span>Sample Rate:</span>
						<span class="font-mono text-zinc-300">{formatFrequency(Number(timing.sample_rate))}</span>
					</div>
					<div class="flex justify-between">
						<span>Duration:</span>
						<span class="font-mono text-zinc-300">{formatTime(Number(timing.duration))}</span>
					</div>
					<div class="flex justify-between">
						<span>Rest Time:</span>
						<span class="font-mono text-zinc-300">{formatTime(Number(timing.rest_time || 0))}</span>
					</div>
					<div class="flex justify-between border-t border-zinc-700 pt-1.5">
						<span>Frequency:</span>
						<span class="font-mono text-zinc-300"
							>{formatFrequency(1 / (Number(timing.duration) + Number(timing.rest_time || 0)))}</span
						>
					</div>
					<div class="flex justify-between">
						<span>Samples:</span>
						<span class="font-mono text-zinc-300"
							>{Math.floor(Number(timing.sample_rate) * Number(timing.duration))}</span
						>
					</div>
				</div>
			</div>
		{/if}
		<div class="rounded border border-zinc-700 bg-zinc-800/50 p-3">
			<ProfileDevicesToggle {manager} bind:visible={visibleDevices} colors={deviceColors} waveformsOnly={true} />
		</div>
		<div class="flex flex-col justify-center gap-2">
			<span class="text-[0.65rem] text-zinc-400">Cycles:</span>
			<SpinBox bind:value={numCycles} min={1} max={4} step={1} numCharacters={1} />
		</div>
	</div>
</div>
