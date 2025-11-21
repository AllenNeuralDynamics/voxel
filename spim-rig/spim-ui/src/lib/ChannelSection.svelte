<script lang="ts">
	import ChannelInfoTooltip from '$lib/ChannelInfoTooltip.svelte';
	import ColorPicker from '$lib/ui/ColorPicker.svelte';
	import Icon from '@iconify/svelte';
	import Histogram from '$lib/preview/Histogram.svelte';
	import { COLORMAP_COLORS } from '$lib/preview/colormap';
	import LaserControl from '$lib/LaserControl.svelte';
	import CameraControl from '$lib/CameraControl.svelte';
	import type { Previewer, PreviewChannel } from '$lib/preview';
	import type { DevicesManager } from '$lib/devices.svelte';

	interface Props {
		channel: PreviewChannel;
		previewer: Previewer;
		devicesManager: DevicesManager;
	}

	let { channel, previewer, devicesManager }: Props = $props();

	// Get preset colors for the color picker
	const presetColors = Object.values(COLORMAP_COLORS);

	function handleColorChange(newColor: string) {
		channel.setColor(newColor);
	}

	function handleVisibilityToggle() {
		channel.visible = !channel.visible;
	}

	function handleLevelsChange(min: number, max: number) {
		if (channel.name) {
			previewer.setChannelLevels(channel.name, min, max);
		}
	}
</script>

<div class="space-y-4 px-4 py-4">
	<!-- Channel Header with Inline Controls -->
	{#if channel.name}
		<div class="-mt-2 flex items-center justify-between">
			<span class="font-medium text-zinc-100" style="color: {channel.color};"
				>{channel.label ?? channel.config?.label ?? channel.name}</span
			>
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
				<ColorPicker color={channel.color} {presetColors} onColorChange={handleColorChange} align="end" />
			</div>
		</div>
	{/if}

	<!-- Histogram -->
	<!-- space-y-2 rounded-lg border border-zinc-700 bg-zinc-900/20  -->
	<!-- <div class="px-3 shadow-sm"> -->
	<Histogram
		histData={channel.latestHistogram}
		levelsMin={channel.levelsMin}
		levelsMax={channel.levelsMax}
		dataTypeMax={65535}
		color={channel.color}
		onLevelsChange={handleLevelsChange}
	/>
	<!-- </div> -->

	<!-- Device Controls -->
	<!-- Illumination -->
	{#if channel.config?.illumination}
		<LaserControl deviceId={channel.config.illumination} {devicesManager} />
	{/if}

	<!-- Detection -->
	{#if channel.config?.detection}
		<CameraControl deviceId={channel.config.detection} {devicesManager} />
	{/if}
</div>
