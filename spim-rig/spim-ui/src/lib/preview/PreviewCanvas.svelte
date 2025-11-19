<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { Previewer } from './previewer.svelte';

	let previewCanvas: HTMLCanvasElement;

	interface PreviewProps {
		previewer: Previewer;
	}

	let { previewer }: PreviewProps = $props();

	onMount(async () => {
		await previewer.init(previewCanvas);
	});

	onDestroy(() => {
		previewer.shutdown();
	});
</script>

<div class="flex h-full w-full flex-col items-start justify-start">
	<canvas
		bind:this={previewCanvas}
		class="preview-canvas max-h-full max-w-full object-contain object-top"
		class:panning={previewer.isPanZoomActive}
	></canvas>
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
