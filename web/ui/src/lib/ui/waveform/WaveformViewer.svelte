<script lang="ts">
	import uPlot from 'uplot';
	import type { Session } from '$lib/main';
	import type { GroupMode, DeviceGroup } from '$lib/main';
	import { onDestroy } from 'svelte';
	import { ToggleGroup, Checkbox, Collapsible } from 'bits-ui';
	import { Check, Minus, ChevronRight } from '$lib/icons';
	import { SvelteSet } from 'svelte/reactivity';
	import SpinBox from '$lib/ui/kit/SpinBox.svelte';
	import 'uplot/dist/uPlot.min.css';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	// Internal state for visible devices
	let visibleDevices = $state(new Set<string>());

	let plotContainer = $state<HTMLDivElement>();
	let chart: uPlot | undefined;
	let containerHeight = $state(400);

	// Get waveforms and timing from session
	const waveforms = $derived(session.waveforms);
	const timing = $derived(session.activeProfileConfig?.daq?.timing);

	let numCycles = $state(1);

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

	// --- Device toggle (inlined from ProfileDevicesToggle) ---

	type UiGroupMode = 'none' | 'type' | 'path' | 'channel';
	let groupMode = $state<UiGroupMode>('none');

	const config = $derived(session.config);

	// Devices with waveforms (those with acq_port in DAQ config)
	const devicesWithWaveforms = $derived.by(() => {
		if (!config?.daq?.acq_ports) return new Set<string>();
		return new Set(Object.keys(config.daq.acq_ports));
	});

	const resolvedMode = $derived<GroupMode>(groupMode === 'none' ? 'role' : groupMode);

	const groups = $derived.by((): DeviceGroup[] => {
		const profileId = session.activeProfileId;
		if (!profileId) return [];

		return session.profileDevices
			.group(profileId, resolvedMode)
			.map((g) => ({
				...g,
				devices: g.devices.filter((d) => devicesWithWaveforms.has(d))
			}))
			.filter((g) => g.devices.length > 0);
	});

	// Initialize visible set with all devices when profile changes
	$effect(() => {
		if (groups.length > 0) {
			const allDevices = new SvelteSet<string>();
			groups.forEach((group) => group.devices.forEach((d) => allDevices.add(d)));
			visibleDevices = allDevices;
		}
	});

	function getGroupCheckState(group: DeviceGroup): { checked: boolean; indeterminate: boolean } {
		const visibleInGroup = group.devices.filter((d) => visibleDevices.has(d)).length;
		if (visibleInGroup === 0) return { checked: false, indeterminate: false };
		if (visibleInGroup === group.devices.length) return { checked: true, indeterminate: false };
		return { checked: false, indeterminate: true };
	}

	function getVisibleCount(group: DeviceGroup): number {
		return group.devices.filter((d) => visibleDevices.has(d)).length;
	}

	function toggleGroup(group: DeviceGroup, checked: boolean) {
		const next = new SvelteSet(visibleDevices);
		if (checked) group.devices.forEach((d) => next.add(d));
		else group.devices.forEach((d) => next.delete(d));
		visibleDevices = next;
	}

	function toggleDevice(deviceId: string, checked: boolean) {
		const next = new SvelteSet(visibleDevices);
		if (checked) next.add(deviceId);
		else next.delete(deviceId);
		visibleDevices = next;
	}
</script>

{#snippet deviceToggle()}
	<div class="flex flex-col gap-2">
		<!-- Mode Toggle -->
		<div class="flex items-center gap-1.5">
			<ToggleGroup.Root type="single" bind:value={groupMode} class="inline-flex rounded border border-zinc-700">
				<ToggleGroup.Item
					value="none"
					class="px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
				>
					All
				</ToggleGroup.Item>
				<ToggleGroup.Item
					value="type"
					class="border-x border-zinc-700 px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
				>
					Type
				</ToggleGroup.Item>
				<ToggleGroup.Item
					value="path"
					class="border-x border-zinc-700 px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
				>
					Path
				</ToggleGroup.Item>
				<ToggleGroup.Item
					value="channel"
					class="px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
				>
					Channel
				</ToggleGroup.Item>
			</ToggleGroup.Root>
		</div>

		<!-- Device Tree -->
		<div class="mt-3 space-y-4">
			{#if groups.length === 0}
				<p class="text-xs text-zinc-500">No devices available</p>
			{:else}
				{#each groups as group (group.id)}
					{@const groupState = getGroupCheckState(group)}
					<Collapsible.Root open={true}>
						<div class="flex items-start gap-0.5">
							<Checkbox.Root
								checked={groupState.checked}
								indeterminate={groupState.indeterminate}
								onCheckedChange={(checked) => toggleGroup(group, checked ?? false)}
								class="mt-0 flex h-3.5 w-3.5 items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors data-[state=checked]:border-emerald-500 data-[state=checked]:bg-emerald-600"
							>
								{#if groupState.checked}
									<Check class="text-white" width="12" height="12" />
								{:else if groupState.indeterminate}
									<Minus class="text-white" width="12" height="12" />
								{/if}
							</Checkbox.Root>

							<Collapsible.Trigger class="flex flex-1 items-center gap-1 text-xs font-medium hover:text-zinc-300">
								<ChevronRight
									class="text-zinc-500 transition-transform data-[state=open]:rotate-90"
									width="14"
									height="14"
								/>
								<span>
									{group.label}
									<span class="text-zinc-500">({getVisibleCount(group)}/{group.devices.length})</span>
								</span>
							</Collapsible.Trigger>
						</div>

						<Collapsible.Content class="mt-3 ml-3.5 space-y-2">
							{#each group.devices as deviceId (deviceId)}
								<label class="flex cursor-pointer items-center gap-2 hover:text-zinc-300">
									<Checkbox.Root
										checked={visibleDevices.has(deviceId)}
										onCheckedChange={(checked) => toggleDevice(deviceId, checked ?? false)}
										class="flex h-3 w-3 items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors data-[state=checked]:border-emerald-500 data-[state=checked]:bg-emerald-600"
									>
										{#if visibleDevices.has(deviceId)}
											<Check class="text-white" width="10" height="10" />
										{/if}
									</Checkbox.Root>
									<span class="text-xs">{deviceId}</span>
									{#if deviceColors[deviceId]}
										<div
											class="ml-auto h-1.5 w-1.5 rounded-full"
											style="background-color: {deviceColors[deviceId]};"
										></div>
									{/if}
								</label>
							{/each}
						</Collapsible.Content>
					</Collapsible.Root>
				{/each}
			{/if}
		</div>
	</div>
{/snippet}

<div class="flex h-full gap-4 p-4">
	<div class="my-4 flex flex-col justify-between gap-2">
		{#if timing}
			<!-- class="rounded border border-zinc-700 bg-zinc-800/50 p-3" -->
			<div class="w-40">
				<h3 class="mb-2 text-xs font-medium text-zinc-300">Acquisition Timing</h3>
				<div class="space-y-1.5 text-[0.65rem] text-zinc-400">
					<div class="flex justify-between">
						<span>Sample Rate</span>
						<span class="font-mono text-zinc-300">{formatFrequency(Number(timing.sample_rate))}</span>
					</div>
					<div class="flex justify-between">
						<span>Duration</span>
						<span class="font-mono text-zinc-300">{formatTime(Number(timing.duration))}</span>
					</div>
					<div class="flex justify-between">
						<span>Rest Time</span>
						<span class="font-mono text-zinc-300">{formatTime(Number(timing.rest_time || 0))}</span>
					</div>
					<div class="flex justify-between border-t border-zinc-700 pt-1.5">
						<span>Frequency</span>
						<span class="font-mono text-zinc-300"
							>{formatFrequency(1 / (Number(timing.duration) + Number(timing.rest_time || 0)))}</span
						>
					</div>
					<div class="flex justify-between">
						<span>Samples</span>
						<span class="font-mono text-zinc-300"
							>{Math.floor(Number(timing.sample_rate) * Number(timing.duration))}</span
						>
					</div>
				</div>
			</div>
		{/if}
		<div class="flex flex-col justify-center gap-2">
			<span class="text-[0.65rem] text-zinc-400">Cycles:</span>
			<SpinBox bind:value={numCycles} min={1} max={4} step={1} numCharacters={1} />
		</div>
	</div>
	<div class="flex flex-1 flex-col">
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

	<div class="mt-4">
		{@render deviceToggle()}
	</div>
</div>
