<script lang="ts">
	import ColorPicker from '$lib/components/ColorPicker.svelte';
	import Histogram from './Histogram.svelte';
	import Icon from '@iconify/svelte';
	import { sanitizeString } from '$lib/utils';
	import { COLORMAP_COLORS } from './colormap';
	import type { Previewer } from './controller.svelte';
	import type { PreviewChannel } from './controller.svelte';

	interface Props {
		channel: PreviewChannel;
		previewer: Previewer;
	}

	let { channel, previewer }: Props = $props();

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

<div class="space-y-2">
	<!-- Channel name and controls -->
	<div class="flex items-center justify-between">
		<span class="font-medium">{channel.name ? sanitizeString(channel.name) : 'Unknown'}</span>
		<div class="flex items-center gap-2">
			<button
				onclick={handleVisibilityToggle}
				class="flex items-center rounded p-1 transition-colors {channel.visible
					? 'text-zinc-400 hover:bg-zinc-800'
					: 'text-zinc-600 hover:bg-zinc-800'}"
				aria-label={channel.visible ? 'Hide channel' : 'Show channel'}
			>
				<Icon icon={channel.visible ? 'mdi:eye' : 'mdi:eye-off'} width="14" height="14" />
			</button>
			<ColorPicker color={channel.color} {presetColors} onColorChange={handleColorChange} align="end" />
		</div>
	</div>

	<!-- Histogram -->
	<Histogram
		histData={channel.latestHistogram}
		levelsMin={channel.levelsMin}
		levelsMax={channel.levelsMax}
		dataTypeMax={65535}
		color={channel.color}
		onLevelsChange={handleLevelsChange}
	/>
</div>
