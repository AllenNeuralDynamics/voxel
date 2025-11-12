<script lang="ts">
	import { Preview, PreviewManager } from '$lib/widgets/preview';
	import { onMount } from 'svelte';

	// Initialize preview manager
	const wsUrl = 'ws://localhost:8000/ws/preview';
	const channelNames = ['red', 'green', 'blue'];
	const manager = new PreviewManager(wsUrl, channelNames);

	onMount(() => {
		// Start preview when component mounts
		return () => {
			// Cleanup handled by Preview component's onDestroy
		};
	});

	function handleStartPreview() {
		manager.startPreview();
	}

	function handleStopPreview() {
		manager.stopPreview();
	}

	function handleResetTransform() {
		manager.resetTransform();
	}
</script>

<div class="flex h-screen w-full flex-col bg-zinc-950 text-zinc-100">
	<header class="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
		<h1 class="text-2xl font-bold">SPIM Preview</h1>
		<div class="flex gap-2">
			<button
				onclick={handleStartPreview}
				disabled={manager.isPreviewing}
				class="rounded bg-emerald-600 px-4 py-2 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
			>
				Start
			</button>
			<button
				onclick={handleStopPreview}
				disabled={!manager.isPreviewing}
				class="rounded bg-rose-600 px-4 py-2 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
			>
				Stop
			</button>
			<button
				onclick={handleResetTransform}
				class="rounded bg-zinc-700 px-4 py-2 text-sm font-medium transition-colors hover:bg-zinc-600"
			>
				Reset View
			</button>
		</div>
	</header>

	<main class="flex-1 overflow-hidden">
		<Preview {manager} />
	</main>
</div>
