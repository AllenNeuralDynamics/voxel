<script lang="ts">
	import ChannelInfoTooltip from '$lib/ui/ChannelInfoTooltip.svelte';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { PreviewChannel } from '$lib/main';
	import type { DevicesManager } from '$lib/main';
	import type { DeviceFilter } from './DeviceFilterToggle.svelte';

	interface Props {
		channel: PreviewChannel;
		devices: DevicesManager;
		deviceFilter: DeviceFilter;
	}

	let { channel, devices: devicesManager, deviceFilter }: Props = $props();

	// Determine which device controls to show based on filter
	const showIllumination = $derived(deviceFilter === 'all' || deviceFilter === 'illumination');
	const showDetection = $derived(deviceFilter === 'all' || deviceFilter === 'detection');

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
</script>

<div class="space-y-4 px-4 py-4">
	<!-- Channel Header -->
	{#if channel.name}
		<div class="-mt-2 flex items-center justify-between">
			<span class="text-xs font-medium text-zinc-200">
				{channel.label ?? channel.config?.label ?? channel.name}
			</span>
			<ChannelInfoTooltip name={channel.name} label={channel.label} config={channel.config} />
		</div>
	{/if}

	<!-- Device Controls -->
	{#if channel.config?.illumination && showIllumination}
		<LaserControl deviceId={channel.config.illumination} {devicesManager} />
	{/if}

	{#if channel.config?.detection && showDetection}
		<CameraControl deviceId={channel.config.detection} {devicesManager} />
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
