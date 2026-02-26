<script lang="ts">
	import { onMount } from 'svelte';
	import PreviewInfoTooltip from './PreviewInfoTooltip.svelte';
	import type { Previewer } from './previewer.svelte';

	let previewCanvas: HTMLCanvasElement;
	let previewCanvasContainer: HTMLDivElement;

	interface PreviewProps {
		previewer: Previewer;
	}

	let { previewer }: PreviewProps = $props();

	// Get frame info from visible channels
	let visibleChannels = $derived(previewer.channels.filter((c) => c.visible && c.latestFrameInfo));

	// Get representative frame info (from first visible channel)
	let frameInfo = $derived(visibleChannels[0]?.latestFrameInfo ?? null);

	// Frame counter
	let maxFrameIdx = $derived(Math.max(...visibleChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0), 0));

	// Prepare channel frame info for tooltip
	let channelFrameInfos = $derived(
		visibleChannels.map((c) => ({
			name: c.name ?? 'Unknown',
			label: c.label,
			frameInfo: c.latestFrameInfo!
		}))
	);

	onMount(async () => {
		// reasonable default
		previewCanvas.height = previewCanvasContainer.clientWidth;
		previewCanvas.width = (previewCanvasContainer.clientWidth * 4) / 3;
		await previewer.init(previewCanvas);
	});

	// Note: Do NOT call previewer.shutdown() here.
	// The App class owns the previewer lifecycle.
	// PreviewCanvas is just a view that uses it.
</script>

<div
	class="relative flex h-full items-start justify-center bg-background px-4 pt-18 pb-8"
	bind:this={previewCanvasContainer}
>
	<canvas
		bind:this={previewCanvas}
		class="preview-canvas max-h-full max-w-full border border-emerald-400"
		class:panning={previewer.isPanZoomActive}
		class:is-idle={!previewer.isPreviewing}
	>
	</canvas>
	<!-- Tooltip overlay -->
	<div class="absolute top-0 right-0 flex h-18 items-center">
		<PreviewInfoTooltip {frameInfo} visibleChannels={channelFrameInfos} />
	</div>
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
</div>

<style>
	.preview-canvas {
		filter: blur(0px);
		transition: filter 0.15s ease-in-out;
	}

	.preview-canvas.panning {
		filter: blur(5px);
	}
	/*.preview-canvas.is-idle {
		opacity: 0.5;
	}*/
</style>
