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

<div class="relative h-full w-full">
	<canvas bind:this={previewCanvas} class="h-full w-full object-contain"></canvas>
</div>
