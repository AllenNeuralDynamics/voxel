<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { PreviewManager } from './manager.svelte';

	let previewCanvas: HTMLCanvasElement;

	interface PreviewProps {
		manager: PreviewManager;
	}

	let { manager }: PreviewProps = $props();

	onMount(async () => {
		await manager.init(previewCanvas);
	});

	onDestroy(() => {
		manager.shutdown();
	});

	// Reactive values for display
	const channelsWithFrames = $derived(manager.channels.filter((c) => c.frameInfo !== null));
	const latestFrameIdx = $derived(channelsWithFrames.length > 0 ? channelsWithFrames[0].frameInfo?.frame_idx : null);

	function toggleChannel(channelName: string) {
		const channel = manager.channels.find((c) => c.name === channelName);
		if (channel) {
			manager.setChannelVisibility(channelName, !channel.visible);
		}
	}

	function getChannelColor(channelName: string): string {
		const name = channelName.toLowerCase();
		if (name.includes('red') || name.includes('mcherry') || name.includes('rfp')) {
			return 'text-rose-400';
		}
		if (name.includes('green') || name.includes('gfp')) {
			return 'text-emerald-400';
		}
		if (name.includes('blue') || name.includes('dapi') || name.includes('bfp')) {
			return 'text-sky-400';
		}
		if (name.includes('cyan') || name.includes('cfp')) {
			return 'text-cyan-400';
		}
		if (name.includes('yellow') || name.includes('yfp')) {
			return 'text-yellow-400';
		}
		return 'text-zinc-400';
	}
</script>

<div class="relative flex h-full w-full flex-col px-4">
	<div class="absolute top-2 left-2 z-10 flex flex-col gap-2">
		<div class="flex flex-col gap-1 rounded-md bg-zinc-900/85 p-2">
			{#each manager.channels as channel (channel.name)}
				<label class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 transition-colors hover:bg-zinc-700/30">
					<input
						type="checkbox"
						checked={channel.visible}
						onchange={() => toggleChannel(channel.name)}
						class="h-4 w-4 cursor-pointer"
					/>
					<span class="text-xs font-semibold select-none {getChannelColor(channel.name)}">
						{channel.name.toUpperCase()}
					</span>
				</label>
			{/each}
		</div>
		<div class="flex items-center gap-4 rounded-md bg-zinc-900/85 px-3 py-1.5">
			{#if latestFrameIdx !== null}
				<span class="text-xs text-zinc-400">Frame {latestFrameIdx}</span>
			{/if}
			<div class="flex items-center gap-2 text-xs text-zinc-400">
				<span
					class="h-2 w-2 rounded-full transition-colors {manager.connectionState === 'connected'
						? 'bg-emerald-500 shadow-[0_0_0.5rem_var(--color-emerald-500)]'
						: 'bg-zinc-500'}"
				></span>
				<span>{manager.statusMessage}</span>
			</div>
		</div>
	</div>
	<canvas bind:this={previewCanvas} class="h-full w-full object-contain"></canvas>
</div>
