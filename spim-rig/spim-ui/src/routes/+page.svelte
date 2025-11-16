<script lang="ts">
	import { PreviewCanvas, Previewer, PreviewChannelControls } from '$lib/preview';
	import { onMount } from 'svelte';

	// Initialize preview controller
	const wsUrl = 'ws://localhost:8000/ws/preview';
	const previewer = new Previewer(wsUrl);

	onMount(() => {
		// Start preview when component mounts
		return () => {
			// Cleanup handled by Preview component's onDestroy
		};
	});

	function handleStartPreview() {
		previewer.startPreview();
	}

	function handleStopPreview() {
		previewer.stopPreview();
	}

	function handleResetCrop() {
		previewer.resetCrop();
	}

	//blue-950
</script>

<div class="flex h-screen w-full flex-col bg-zinc-950 text-zinc-100">
	<!-- <header class="border-b border-zinc-800 bg-slate-900 px-6 py-1">
		<h1 class="text-xs font-bold">SPIM PREVIEW</h1>
	</header> -->

	<main class="flex flex-1 flex-col overflow-hidden">
		<div class="flex flex-1 overflow-hidden">
			<aside class="flex w-80 flex-col border-r border-zinc-800 bg-zinc-900/50">
				{#if previewer.channels.length === 0}
					<div class="flex flex-1 items-center justify-center">
						<p class="text-sm text-zinc-500">No channels available</p>
					</div>
				{:else}
					<div class="flex flex-1 flex-col overflow-y-auto">
						{#each previewer.channels as channel (channel.idx)}
							{#if channel.name}
								<div class="space-y-2 border-b border-zinc-800 px-3 pt-4 pb-6">
									<!-- Preview Section -->
									<PreviewChannelControls {channel} {previewer} />

									<div class="space-y-2 pt-2">
										<!-- Detection Section (placeholder) -->
										<div class="space-y-1">
											<div class="text-[0.5rem] font-semibold text-zinc-400 uppercase">Detection</div>
											<div class="h-16 py-1">
												<div class="text-[0.6rem] text-zinc-500">Exposure, gain, binning controls...</div>
											</div>
										</div>

										<!-- Illumination Section (placeholder) -->
										<div class="space-y-1">
											<div class="text-[0.5rem] font-semibold text-zinc-400 uppercase">Illumination</div>
											<div class="h-16 py-1">
												<div class="text-[0.6rem] text-zinc-500">Power, focus, shutter controls...</div>
											</div>
										</div>
									</div>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			</aside>

			<div class="flex-1">
				<PreviewCanvas {previewer} />
			</div>
		</div>

		<footer class="flex items-center justify-between border-t border-zinc-800 px-6 py-3">
			<div class="flex items-center gap-2 text-xs text-zinc-400">
				<span
					class="h-2.5 w-2.5 rounded-full transition-colors {previewer.connectionState
						? 'bg-emerald-500 shadow-[0_0_0.5rem_--theme(--color-emerald-500/50)]'
						: 'bg-zinc-500'}"
				></span>
				<span>{previewer.statusMessage}</span>
			</div>

			<div class="flex items-center gap-4 text-xs text-zinc-400">
				<span>Zoom: {previewer.crop.k.toFixed(2)}</span>
				<span>X: {previewer.crop.x.toFixed(2)}</span>
				<span>Y: {previewer.crop.y.toFixed(2)}</span>
				<button
					onclick={handleResetCrop}
					class="rounded bg-zinc-800 px-2 py-0.5 text-[0.65rem] text-zinc-300 transition-colors hover:bg-zinc-700"
					aria-label="Reset pan and zoom"
				>
					Reset
				</button>
			</div>

			<div class="flex gap-2">
				<button
					onclick={handleStartPreview}
					disabled={previewer.isPreviewing}
					class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Start
				</button>
				<button
					onclick={handleStopPreview}
					disabled={!previewer.isPreviewing}
					class="rounded bg-rose-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Stop
				</button>
			</div>
		</footer>
	</main>
</div>
