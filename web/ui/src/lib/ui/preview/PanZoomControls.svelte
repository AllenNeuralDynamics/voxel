<script lang="ts">
	import { Restore } from '$lib/icons';
	import { SpinBox } from '$lib/ui/kit';
	import type { PreviewState } from '$lib/main';

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

<div class="flex items-center gap-1 font-mono text-[0.65rem]">
	<button
		onclick={() => previewer.resetCrop()}
		disabled={isDefaultCrop}
		class="flex items-center rounded p-1 text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-0"
		aria-label="Reset pan and zoom"
	>
		<Restore width="12" height="12" />
	</button>
	<div class="flex items-center gap-4">
		<SpinBox
			bind:value={magnification}
			min={1}
			max={100}
			step={0.1}
			snapValue={1}
			decimals={1}
			numCharacters={5}
			size="sm"
			prefix="Zoom"
			suffix="x"
			onChange={handleZoomChange}
		/>
		<SpinBox
			bind:value={cropY}
			min={0}
			max={1}
			step={0.01}
			snapValue={0}
			decimals={2}
			numCharacters={5}
			size="sm"
			prefix="Pan X"
			onChange={handleCropYChange}
		/>
		<SpinBox
			bind:value={cropX}
			min={0}
			max={1}
			step={0.01}
			snapValue={0}
			decimals={2}
			numCharacters={5}
			size="sm"
			prefix="Pan Y"
			onChange={handleCropXChange}
		/>
	</div>
</div>
