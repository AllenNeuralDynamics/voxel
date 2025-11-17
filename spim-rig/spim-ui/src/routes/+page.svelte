<script lang="ts">
	import { PreviewCanvas, Previewer, PreviewChannelControls, PreviewInfo } from '$lib/preview';
	import { onMount } from 'svelte';

	// Initialize preview controller
	const wsUrl = 'ws://localhost:8000/ws/preview';
	const previewer = new Previewer(wsUrl);

	onMount(() => {
		// Start preview when component mounts ... likely not since lasers also turn on and might cause bleaching.
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

	//blue-950
</script>

<div class="flex h-screen w-full flex-col bg-zinc-950 text-zinc-100">
	<!-- <header class="border-b border-zinc-800 bg-slate-900 px-6 py-1">
		<h1 class="text-xs font-bold">SPIM PREVIEW</h1>
	</header> -->

	<main class="flex flex-1 flex-col overflow-hidden">
		<div class="flex flex-1 overflow-hidden">
			<aside class="flex w-96 flex-col gap-2 border-r border-zinc-800 p-3">
				{#if previewer.channels.length === 0}
					<div class="flex flex-1 items-center justify-center">
						<p class="text-sm text-zinc-500">No channels available</p>
					</div>
				{:else}
					<div class="flex flex-1 flex-col gap-4 overflow-y-auto">
						{#each previewer.channels as channel (channel.idx)}
							{#if channel.name}
								<div class="space-y-2 rounded-xl border border-zinc-800 bg-zinc-900/70 px-3 pt-4 pb-6">
									<!-- Preview Section -->
									<PreviewChannelControls {channel} {previewer} />

									<div class="space-y-2 pt-2">
										<!-- Detection Section (placeholder) -->
										<div class="space-y-1">
											<div class="text-[0.75rem] text-zinc-500 uppercase">Detection</div>
											<div class="h-16 py-1">
												<div class="text-[0.6rem] text-zinc-500">Exposure, gain, binning controls...</div>
											</div>
										</div>

										<!-- Illumination Section (placeholder) -->
										<div class="space-y-1">
											<div class="text-[0.75rem] font-semibold text-zinc-500 uppercase">Illumination</div>
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

			<PreviewInfo {previewer} />

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
