<script lang="ts">
	import { onMount } from 'svelte';
	import FrameCounter from './FrameCounter.svelte';
	import PreviewInfoTooltip from './PreviewInfoTooltip.svelte';
	import type { Previewer } from './previewer.svelte';

	let previewCanvas: HTMLCanvasElement;

	interface PreviewProps {
		previewer: Previewer;
	}

	let { previewer }: PreviewProps = $props();

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

	onMount(async () => {
		await previewer.init(previewCanvas);
	});

	// Note: Do NOT call previewer.shutdown() here.
	// The App class owns the previewer lifecycle.
	// PreviewCanvas is just a view that uses it.
</script>

<div class="relative flex h-full items-start justify-center bg-zinc-950 px-4 pt-18 pb-12">
	<canvas
		bind:this={previewCanvas}
		class="preview-canvas max-h-full max-w-full border border-emerald-400"
		class:panning={previewer.isPanZoomActive}
		class:is-idle={!previewer.isPreviewing}
	>
	</canvas>
	<!-- Tooltip overlay -->
	<div class="absolute top-0 right-4 flex h-18 items-center">
		<PreviewInfoTooltip {frameInfo} visibleChannels={channelFrameInfos} />
	</div>
	<div class="absolute top-0 left-4 flex h-18 items-center">
		<FrameCounter {previewer} />
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
