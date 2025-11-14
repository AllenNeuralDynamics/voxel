<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { Previewer } from './controller.svelte';

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

<div class="relative flex h-full w-full items-start justify-center px-8 py-4">
	<canvas
		bind:this={previewCanvas}
		class="preview-canvas h-full w-full object-contain object-top"
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
