<script lang="ts">
	import PreviewInfoTooltip from './PreviewInfoTooltip.svelte';
	import PanZoomControls from './PanZoomControls.svelte';
	import type { PreviewState } from '$lib/app/preview.svelte';

	interface Props {
		previewer: PreviewState;
	}

	let { previewer }: Props = $props();

	// Get frame info from visible channels
	let visibleChannels = $derived(previewer.channels.filter((c) => c.visible && c.latestFrameInfo));

	// Get representative frame info (from first visible channel)
	let frameInfo = $derived(visibleChannels[0]?.latestFrameInfo ?? null);

	// Prepare channel frame info for tooltip
	let channelFrameInfos = $derived(
		visibleChannels.map((c) => ({
			name: c.name ?? 'Unknown',
			label: c.label,
			frameInfo: c.latestFrameInfo!
		}))
	);

	// Frame counter
	let frameIndices = $derived(visibleChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0));
	let maxFrameIdx = $derived(Math.max(...frameIndices, 0));
</script>

<!-- Top left: frame counter -->
<div class="absolute top-0 left-0 flex h-18 items-center">
	{#if frameInfo}
		<div class="flex items-center gap-1.5 font-mono text-[0.65rem]">
			<span class="text-zinc-400">Frame</span>
			<span class="text-zinc-300">#{maxFrameIdx}</span>
		</div>
	{:else}
		<span class="font-mono text-[0.65rem] text-zinc-500">No frames</span>
	{/if}
</div>

<!-- Top right: pan/zoom controls + info tooltip -->
<div class="absolute top-0 right-0 flex h-18 items-center gap-4">
	<PanZoomControls {previewer} />
	<PreviewInfoTooltip {frameInfo} visibleChannels={channelFrameInfos} />
</div>
