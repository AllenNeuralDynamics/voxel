<script lang="ts">
	import ColorPicker from './ColorPicker.svelte';
	import Histogram from './Histogram.svelte';
	import Icon from '@iconify/svelte';
	import { sanitizeString } from '$lib/utils';
	import type { Previewer } from '$lib/widgets/preview/controller.svelte';
	import type { PreviewChannel } from '$lib/widgets/preview/controller.svelte';

	interface Props {
		channel: PreviewChannel;
		previewer: Previewer;
	}

	let { channel, previewer }: Props = $props();

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
	<!-- Channel name, frame info, and controls -->
	<div class="flex items-center justify-between gap-3">
		<span class="font-medium">{channel.name ? sanitizeString(channel.name) : 'Unknown'}</span>
		<div class="flex items-center gap-2">
			{#if channel.latestFrameInfo}
				<div class="flex items-center gap-2 font-mono text-[0.6rem] text-zinc-500">
					<span>{channel.latestFrameInfo.preview_width} × {channel.latestFrameInfo.preview_height} px</span>
					<span># {channel.latestFrameInfo.frame_idx}</span>
				</div>
				<div class="h-3 w-px bg-zinc-700"></div>
			{/if}
			<button
				onclick={handleVisibilityToggle}
				class="flex items-center gap-1 rounded p-1 transition-colors {channel.visible
					? 'text-zinc-500 hover:bg-zinc-800'
					: 'text-zinc-700 hover:bg-zinc-800'}"
				aria-label={channel.visible ? 'Hide channel' : 'Show channel'}
			>
				<Icon icon={channel.visible ? 'mdi:eye' : 'mdi:eye-off'} width="14" height="14" />
			</button>
			<ColorPicker color={channel.color} onColorChange={handleColorChange} align="end" />
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
