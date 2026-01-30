<script lang="ts">
	import ChannelInfoTooltip from './ChannelInfoTooltip.svelte';
	import ColormapPicker from './ColormapPicker.svelte';
	import Icon from '@iconify/svelte';
	import { Histogram } from '$lib/ui/preview';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { PreviewState, PreviewChannel } from '$lib/app/preview.svelte';
	import type { DevicesManager, ColormapCatalog } from '$lib/core';
	import type { DeviceFilter } from './DeviceFilterToggle.svelte';

	interface Props {
		channel: PreviewChannel;
		previewer: PreviewState;
		devices: DevicesManager;
		deviceFilter: DeviceFilter;
		showHistograms: boolean;
		catalog: ColormapCatalog;
	}

	let { channel, previewer, devices: devicesManager, deviceFilter, showHistograms, catalog }: Props = $props();

	function handleVisibilityToggle() {
		channel.visible = !channel.visible;
	}

	function handleLevelsChange(min: number, max: number) {
		if (channel.name) {
			previewer.setChannelLevels(channel.name, min, max);
		}
	}

	// Determine which device controls to show based on filter
	const showIllumination = $derived(deviceFilter === 'all' || deviceFilter === 'illumination');
	const showDetection = $derived(deviceFilter === 'all' || deviceFilter === 'detection');
	const showAuxiliary = $derived(deviceFilter === 'all' || deviceFilter === 'auxiliary');

	// Get device status for footer when hidden
	const laserEnabled = $derived(
		channel.config?.illumination
			? devicesManager.getPropertyValue(channel.config.illumination, 'is_enabled')
			: undefined
	);
	const laserPower = $derived(
		channel.config?.illumination ? devicesManager.getPropertyValue(channel.config.illumination, 'power_mw') : undefined
	);

	const cameraFrameRate = $derived(
		channel.config?.detection ? devicesManager.getPropertyValue(channel.config.detection, 'frame_rate_hz') : undefined
	);
	const cameraExposure = $derived(
		channel.config?.detection
			? devicesManager.getPropertyValue(channel.config.detection, 'exposure_time_ms')
			: undefined
	);
	const cameraStreamInfo = $derived(
		channel.config?.detection ? devicesManager.getPropertyValue(channel.config.detection, 'stream_info') : undefined
	);

	const isStreaming = $derived(cameraStreamInfo && cameraStreamInfo !== null && cameraStreamInfo !== undefined);

	// Resolve colormap name to gradient color stops for the histogram
	const colormapColors = $derived.by(() => {
		const name = channel.colormap;
		if (!name) return undefined;
		// Check if it's a direct hex color
		if (name.startsWith('#')) return [name];
		for (const group of catalog) {
			const stops = group.colormaps[name];
			if (stops) return stops;
		}
		return undefined;
	});
</script>

<div class="space-y-4 px-4 py-4">
	<!-- Channel Header with Inline Controls -->
	{#if channel.name}
		<div class="-mt-2 flex items-center justify-between">
			<ColormapPicker
				label={channel.label ?? channel.config?.label ?? channel.name ?? ''}
				colormap={channel.colormap}
				{catalog}
				onColormapChange={(cmap) => {
					if (channel.name) previewer.setChannelColormap(channel.name, cmap);
				}}
			/>
			<div class="flex items-center gap-2">
				<ChannelInfoTooltip name={channel.name} label={channel.label} config={channel.config} />
				<button
					onclick={handleVisibilityToggle}
					class="flex items-center rounded p-1 transition-colors {channel.visible
						? 'text-zinc-300 hover:bg-zinc-800'
						: 'text-zinc-500 hover:bg-zinc-800'}"
					aria-label={channel.visible ? 'Hide channel' : 'Show channel'}
				>
					<Icon icon={channel.visible ? 'mdi:eye' : 'mdi:eye-off'} width="14" height="14" />
				</button>
			</div>
		</div>
	{/if}

	<!-- Histogram -->
	{#if showHistograms}
		<Histogram
			histData={channel.latestHistogram}
			levelsMin={channel.levelsMin}
			levelsMax={channel.levelsMax}
			dataTypeMax={65535}
			colors={colormapColors}
			onLevelsChange={handleLevelsChange}
		/>
	{/if}

	<!-- Device Controls -->
	<!-- Illumination -->
	{#if channel.config?.illumination && showIllumination}
		<LaserControl deviceId={channel.config.illumination} {devicesManager} />
	{/if}

	<!-- Detection -->
	{#if channel.config?.detection && showDetection}
		<CameraControl deviceId={channel.config.detection} {devicesManager} />
	{/if}

	<!-- Auxilliary -->
	{#if channel.config && showAuxiliary}
		<div class="text-[0.5rem] text-zinc-600"></div>
	{/if}

	{#snippet statusItemDivider()}
		<div class="mx-3 h-2.5 w-px bg-zinc-500"></div>
	{/snippet}
	{#snippet statusBarLabel(label: string)}
		<span class="text-zinc-400/90">{label}:</span>
	{/snippet}

	<!-- Device Status Footer (when devices are hidden) -->
	<div class="space-y-1 font-mono text-[0.6rem] text-zinc-300">
		{#if channel.config?.illumination && !showIllumination}
			{@const isActive = typeof laserEnabled === 'boolean' && laserEnabled}
			<div class="flex items-center justify-between py-1">
				{@render statusBarLabel('Illumination')}
				<div class="flex items-center">
					{#if typeof laserPower === 'number'}
						<div>{laserPower.toFixed(1)} mW</div>
					{/if}
					<div class="ml-3 h-1.5 w-1.5 rounded-full {isActive ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
				</div>
			</div>
		{/if}

		{#if channel.config?.detection && !showDetection}
			<div class="flex items-center justify-between py-1">
				{@render statusBarLabel('Detection')}
				<div class="flex items-center">
					{#if typeof cameraFrameRate === 'number'}
						<span>{cameraFrameRate.toFixed(1)} Hz</span>
					{/if}
					{#if typeof cameraExposure === 'number'}
						{@render statusItemDivider()}
						<span>{cameraExposure.toFixed(1)} ms</span>
					{/if}
					<div class="ml-3 h-1.5 w-1.5 rounded-full {isStreaming ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
				</div>
			</div>
		{/if}
	</div>
</div>
