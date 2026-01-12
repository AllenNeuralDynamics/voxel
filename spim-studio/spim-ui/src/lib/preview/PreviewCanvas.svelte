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

<div class="relative inline-block">
	<canvas
		bind:this={previewCanvas}
		class="preview-canvas max-h-full w-full object-contain object-top"
		class:panning={previewer.isPanZoomActive}
	>
	</canvas>

	<!-- Tooltip overlay -->
	<div class="absolute top-2 right-2">
		<PreviewInfoTooltip {frameInfo} visibleChannels={channelFrameInfos} />
	</div>
	<div class="absolute top-2 left-2">
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
</style>
