<script lang="ts">
	import Icon from '@iconify/svelte';
	import DraggableNumberInput from '$lib/ui/primitives/SpinBox.svelte';
	import type { PreviewState } from '$lib/app/preview.svelte';

	interface Props {
		previewer: PreviewState;
	}

	let { previewer }: Props = $props();

	// Check if crop is at default (no pan/zoom)
	let isDefaultCrop = $derived(previewer.crop.x === 0 && previewer.crop.y === 0 && previewer.crop.k === 0);

	// Local state for crop values (for draggable inputs)
	let cropX = $state(0);
	let cropY = $state(0);
	let magnification = $state(1);

	// Sync local state with previewer (runs before DOM update)
	$effect.pre(() => {
		cropX = previewer.crop.x;
		cropY = previewer.crop.y;
		magnification = 1 / (1 - previewer.crop.k);
	});

	function handleCropXChange(value: number) {
		previewer.setCrop({ ...previewer.crop, x: value });
	}

	function handleCropYChange(value: number) {
		previewer.setCrop({ ...previewer.crop, y: value });
	}

	function handleZoomChange(value: number) {
		const k = 1 - 1 / value;
		previewer.setCrop({ ...previewer.crop, k: Math.max(0, Math.min(0.99, k)) });
	}
</script>

<div class="flex items-center gap-4 font-mono text-[0.65rem]">
	<!-- Pan/Zoom section -->
	<div class="flex items-center gap-4">
		<button
			onclick={() => previewer.resetCrop()}
			disabled={isDefaultCrop}
			class="flex items-center rounded p-1 text-zinc-300 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
			aria-label="Reset pan and zoom"
		>
			<Icon icon="mdi:restore" width="12" height="12" />
		</button>
		<div class="flex items-center gap-1.5">
			<span class="text-zinc-400">Zoom</span>
			<DraggableNumberInput
				bind:value={magnification}
				min={1}
				max={100}
				step={0.1}
				decimals={1}
				numCharacters={5}
				onChange={handleZoomChange}
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
				onChange={handleCropXChange}
			/>
			<span class="text-zinc-500">,</span>
			<DraggableNumberInput
				bind:value={cropY}
				min={0}
				max={1}
				step={0.01}
				decimals={2}
				numCharacters={5}
				onChange={handleCropYChange}
			/>
		</div>
	</div>
</div>
