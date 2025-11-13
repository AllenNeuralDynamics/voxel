<script lang="ts">
	import { Preview, Previewer, ColormapType } from '$lib/widgets/preview';
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

	function toggleChannelVisibility(i: number) {
		const channel = previewer.channels[i];
		if (channel) {
			channel.visible = !channel.visible;
		}
	}

	// Helper to get colormap display color
	function getColormapColor(colormap: ColormapType): string {
		const colors: Record<ColormapType, string> = {
			[ColormapType.NONE]: '#ffffff',
			[ColormapType.GRAY]: '#888888',
			[ColormapType.RED]: '#ff0000',
			[ColormapType.GREEN]: '#00ff00',
			[ColormapType.BLUE]: '#0000ff',
			[ColormapType.CYAN]: '#00ffff',
			[ColormapType.MAGENTA]: '#ff00ff',
			[ColormapType.YELLOW]: '#ffff00',
			[ColormapType.ORANGE]: '#ff8800'
		};
		return colors[colormap] || '#ffffff';
	}
</script>

<div class="flex h-screen w-full flex-col bg-zinc-950 text-zinc-100">
	<header class="flex items-center justify-between border-r border-b border-zinc-800 px-6 py-4">
		<h1 class="text-2xl font-bold">SPIM Preview</h1>
		<div class="flex items-center gap-4">
			<div
				class="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-xs text-zinc-400"
			>
				<div class="flex items-center gap-2">
					<span
						class="h-2.5 w-2.5 rounded-full transition-colors {previewer.connectionState
							? 'bg-emerald-500 shadow-[0_0_0.5rem_--theme(--color-emerald-500/50)]'
							: 'bg-zinc-500'}"
					></span>
					<span>{previewer.statusMessage}</span>
				</div>
			</div>
			<div class="flex gap-2">
				<button
					onclick={handleStartPreview}
					disabled={previewer.isPreviewing}
					class="rounded bg-emerald-600 px-4 py-2 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Start
				</button>
				<button
					onclick={handleStopPreview}
					disabled={!previewer.isPreviewing}
					class="rounded bg-rose-600 px-4 py-2 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Stop
				</button>
			</div>
		</div>
	</header>

	<main class="flex flex-1 overflow-hidden">
		<!-- Channel Controls Sidebar -->
		<aside class="flex w-80 flex-col border-r border-zinc-800">
			<div class="flex-1 overflow-y-auto p-4">
				<!-- Crop Info -->
				<div class="mb-4 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3">
					<div class="mb-2 flex items-center justify-between">
						<h3 class="text-sm font-medium">View Crop</h3>
						<button
							onclick={handleResetCrop}
							class="rounded bg-zinc-800 px-2 py-1 text-[0.7rem] font-medium text-zinc-300 transition-colors hover:bg-zinc-700"
						>
							Reset
						</button>
					</div>
					<div class="space-y-1 text-xs text-zinc-400">
						<div class="flex justify-between">
							<span>X (pan):</span>
							<span class="font-mono text-zinc-300">{previewer.crop.x.toFixed(3)}</span>
						</div>
						<div class="flex justify-between">
							<span>Y (pan):</span>
							<span class="font-mono text-zinc-300">{previewer.crop.y.toFixed(3)}</span>
						</div>
						<div class="flex justify-between">
							<span>K (zoom):</span>
							<span class="font-mono text-zinc-300">{previewer.crop.k.toFixed(3)}</span>
						</div>
					</div>
				</div>

				<h2 class="mb-4 text-lg font-semibold">Channels</h2>

				{#if previewer.channels.length === 0}
					<p class="text-sm text-zinc-500">No channels available</p>
				{:else}
					<div class="space-y-3">
						{#each previewer.channels as channel (channel.idx)}
							<div class="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
								<!-- Channel Header -->
								<div class="mb-3 flex items-center justify-between">
									<div class="flex items-center gap-2">
										<!-- Color indicator -->
										<div
											class="h-4 w-4 rounded-full border border-zinc-600"
											style="background-color: {getColormapColor(channel.colormap)}"
										></div>
										<span class="font-medium">{channel.name}</span>
									</div>

									<!-- Visibility toggle -->

									<button
										onclick={() => toggleChannelVisibility(channel.idx)}
										class="rounded px-2 py-1 text-xs transition-colors {channel.visible
											? 'bg-emerald-600 hover:bg-emerald-700'
											: 'bg-zinc-700 hover:bg-zinc-600'}"
									>
										{channel.visible ? 'Visible' : 'Hidden'}
									</button>
								</div>

								<!-- Channel Info -->
								<div class="space-y-2 text-xs text-zinc-400">
									{#if channel.name}
										<div class="flex justify-between">
											<span>Colormap:</span>
											<span class="text-zinc-300">{channel.colormap}</span>
										</div>
										<div class="flex justify-between">
											<span>Intensity:</span>
											<span class="text-zinc-300">
												{(channel.intensityMin * 100).toFixed(0)}% - {(channel.intensityMax * 100).toFixed(0)}%
											</span>
										</div>
										{#if channel.latestFrameInfo}
											<div class="flex justify-between">
												<span>Frame:</span>
												<span class="text-zinc-300">#{channel.latestFrameInfo.frame_idx}</span>
											</div>
											<div class="flex justify-between">
												<span>Size:</span>
												<span class="text-zinc-300">
													{channel.latestFrameInfo.preview_width}×{channel.latestFrameInfo.preview_height}
												</span>
											</div>
										{/if}
									{:else}
										<p class="text-xs text-zinc-500">Unassigned</p>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
			<div class="border-t border-zinc-800 p-4">
				<button
					onclick={handleResetCrop}
					class="w-full rounded bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
				>
					Reset View
				</button>
			</div>
		</aside>

		<!-- Preview Canvas -->
		<div class="flex-1">
			<Preview {previewer} />
		</div>
	</main>
</div>
