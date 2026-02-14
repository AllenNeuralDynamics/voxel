<script lang="ts">
	import { SpinBox } from '$lib/ui/primitives';
	import type { App } from '$lib/app';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	let gridOffsetXMm = $derived(app.gridConfig.x_offset_um / 1000);
	let gridOffsetYMm = $derived(app.gridConfig.y_offset_um / 1000);
	let stepX = $derived(app.fov.width * (1 - app.gridConfig.overlap));
	let stepY = $derived(app.fov.height * (1 - app.gridConfig.overlap));
	let maxOffsetX = $derived(stepX);
	let maxOffsetY = $derived(stepY);

	function updateGridOffsetX(value: number) {
		if (app.gridLocked) return;
		app.setGridOffset(value * 1000, app.gridConfig.y_offset_um);
	}

	function updateGridOffsetY(value: number) {
		if (app.gridLocked) return;
		app.setGridOffset(app.gridConfig.x_offset_um, value * 1000);
	}

	function updateGridOverlap(value: number) {
		if (app.gridLocked) return;
		app.setGridOverlap(value);
	}
</script>

<div
	class="flex items-center gap-2 text-[0.65rem]"
	class:opacity-70={app.gridLocked}
	class:pointer-events-none={app.gridLocked}
>
	<SpinBox
		value={gridOffsetXMm}
		min={-maxOffsetX}
		max={maxOffsetX}
		step={0.1}
		decimals={1}
		numCharacters={5}
		size="sm"
		prefix="Grid dX"
		suffix="mm"
		onChange={updateGridOffsetX}
	/>
	<SpinBox
		value={gridOffsetYMm}
		min={-maxOffsetY}
		max={maxOffsetY}
		step={0.1}
		decimals={1}
		numCharacters={5}
		size="sm"
		prefix="Grid dY"
		suffix="mm"
		onChange={updateGridOffsetY}
	/>
	<SpinBox
		value={app.gridConfig.overlap}
		min={0}
		max={0.5}
		step={0.01}
		decimals={2}
		numCharacters={5}
		size="sm"
		prefix="Overlap"
		suffix="%"
		onChange={updateGridOverlap}
	/>
</div>
