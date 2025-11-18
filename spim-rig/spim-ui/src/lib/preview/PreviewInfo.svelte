<script lang="ts">
	import Icon from '@iconify/svelte';
	import DraggableNumberInput from '$lib/components/DraggableNumberInput.svelte';
	import type { Previewer } from './previewer.svelte';

	interface Props {
		previewer: Previewer;
	}

	let { previewer }: Props = $props();

	// Get frame info from visible channels
	let visibleChannels = $derived(previewer.channels.filter((c) => c.visible && c.latestFrameInfo));

	// Check if all channels have matching frame info
	let hasMismatch = $derived(() => {
		if (visibleChannels.length <= 1) return false;
		const first = visibleChannels[0].latestFrameInfo;
		if (!first) return false;
		return visibleChannels.some((c) => {
			const info = c.latestFrameInfo;
			if (!info) return true;
			return (
				info.preview_width !== first.preview_width ||
				info.preview_height !== first.preview_height ||
				info.full_width !== first.full_width ||
				info.full_height !== first.full_height
			);
		});
	});

	// Get representative frame info (from first visible channel)
	let frameInfo = $derived(visibleChannels[0]?.latestFrameInfo ?? null);

	// Calculate FPS from frame indices (simple approximation)
	let frameIndices = $derived(visibleChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0));
	let maxFrameIdx = $derived(Math.max(...frameIndices, 0));

	// Check if crop is at default (no pan/zoom)
	let isDefaultCrop = $derived(previewer.crop.x === 0 && previewer.crop.y === 0 && previewer.crop.k === 0);

	// Local state for crop values (for draggable inputs)
	let cropX = $state(previewer.crop.x);
	let cropY = $state(previewer.crop.y);
	let magnification = $state(1 / (1 - previewer.crop.k));

	// Sync local state with previewer
	$effect(() => {
		cropX = previewer.crop.x;
		cropY = previewer.crop.y;
		magnification = 1 / (1 - previewer.crop.k);
	});

	function handleCropXChange(value: number) {
		previewer.crop = { ...previewer.crop, x: value };
	}

	function handleCropYChange(value: number) {
		previewer.crop = { ...previewer.crop, y: value };
	}

	function handleZoomChange(value: number) {
		const k = 1 - 1 / value;
		previewer.crop = { ...previewer.crop, k: Math.max(0, Math.min(0.99, k)) };
	}

	function handleResetCrop() {
		previewer.resetCrop();
	}
</script>

<div class="flex items-center gap-4 font-mono text-[0.65rem]">
	<!-- Frame info section -->
	{#if frameInfo}
		<div class="flex items-center gap-4">
			<!-- Frame counter -->
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-400">Frame</span>
				<span class="text-zinc-300">#{maxFrameIdx}</span>
			</div>

			<!-- Preview dimensions -->
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-400">Preview</span>
				<span class="text-zinc-300">{frameInfo.preview_width} × {frameInfo.preview_height}</span>
			</div>

			<!-- Full frame dimensions -->
			{#if frameInfo.full_width !== frameInfo.preview_width || frameInfo.full_height !== frameInfo.preview_height}
				<div class="flex items-center gap-1.5">
					<span class="text-zinc-400">Full</span>
					<span class="text-zinc-300">{frameInfo.full_width} × {frameInfo.full_height}</span>
				</div>
			{/if}

			<!-- Mismatch warning -->
			{#if hasMismatch()}
				<div class="text-amber-400" title="Channels have mismatched frame info">
					<Icon icon="mdi:alert" width="12" height="12" />
				</div>
			{/if}
		</div>
	{:else}
		<span class="text-zinc-500">No frames</span>
	{/if}

	<!-- Separator -->
	<div class="h-3 w-px bg-zinc-700"></div>

	<!-- Pan/Zoom section -->
	<div class="flex items-center gap-4">
		<div class="flex items-center gap-1.5">
			<span class="text-zinc-400">Zoom</span>
			<DraggableNumberInput
				bind:value={magnification}
				min={1}
				max={100}
				step={0.1}
				decimals={1}
				numCharacters={5}
				onValueChange={handleZoomChange}
			/>
			<span class="text-zinc-300">x</span>
		</div>

		<div class="flex items-center gap-1.5">
			<span class="text-zinc-400">Pan</span>
			<DraggableNumberInput
				bind:value={cropX}
				min={0}
				max={1}
				step={0.01}
				decimals={2}
				numCharacters={5}
				onValueChange={handleCropXChange}
			/>
			<span class="text-zinc-500">,</span>
			<DraggableNumberInput
				bind:value={cropY}
				min={0}
				max={1}
				step={0.01}
				decimals={2}
				numCharacters={5}
				onValueChange={handleCropYChange}
			/>
		</div>

		<button
			onclick={handleResetCrop}
			disabled={isDefaultCrop}
			class="flex items-center rounded p-1 text-zinc-300 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
			aria-label="Reset pan and zoom"
		>
			<Icon icon="mdi:restore" width="12" height="12" />
		</button>
	</div>
</div>
