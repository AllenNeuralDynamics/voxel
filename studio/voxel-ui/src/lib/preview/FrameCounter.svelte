<script lang="ts">
	import type { Previewer } from '$lib/preview';

	interface Props {
		previewer: Previewer;
	}

	let { previewer }: Props = $props();

	// Get frame info from visible channels
	let visibleChannels = $derived(previewer.channels.filter((c) => c.visible && c.latestFrameInfo));

	// Get representative frame info (from first visible channel)
	let frameInfo = $derived(visibleChannels[0]?.latestFrameInfo ?? null);

	// Calculate max frame index from all visible channels
	let frameIndices = $derived(visibleChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0));
	let maxFrameIdx = $derived(Math.max(...frameIndices, 0));
</script>

{#if frameInfo}
	<div class="flex items-center gap-1.5 font-mono text-[0.65rem]">
		<span class="text-zinc-400">Frame</span>
		<span class="text-zinc-300">#{maxFrameIdx}</span>
	</div>
{:else}
	<span class="font-mono text-[0.65rem] text-zinc-500">No frames</span>
{/if}
