<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Button, SpinBox } from '$lib/ui/primitives';
	import type { App } from '$lib/app';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Grid offset state
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

	// Stage position state
	let xAxis = $derived(app.xAxis);
	let yAxis = $derived(app.yAxis);
	let zAxis = $derived(app.zAxis);

	let posX = $state(0);
	let posY = $state(0);
	let posZ = $state(0);

	$effect.pre(() => {
		if (xAxis) posX = xAxis.position;
	});

	$effect.pre(() => {
		if (yAxis) posY = yAxis.position;
	});

	$effect.pre(() => {
		if (zAxis) posZ = zAxis.position;
	});

	function handleXChange(value: number) {
		xAxis?.move(value);
	}

	function handleYChange(value: number) {
		yAxis?.move(value);
	}

	function handleZChange(value: number) {
		zAxis?.move(value);
	}
</script>

<div class="flex items-start gap-2 text-[0.65rem]">
	<div class="flex flex-1 flex-wrap items-center justify-between gap-x-8 gap-y-2">
		<div
			class="flex items-center gap-2"
			class:opacity-70={app.gridLocked}
			class:pointer-events-none={app.gridLocked}
		>
			<SpinBox
				value={gridOffsetXMm}
				min={-maxOffsetX}
				max={maxOffsetX}
				step={0.1}
				decimals={1}
				size="sm"
				prefix="Grid dX"
				suffix="mm"
				class="w-32"
				onChange={updateGridOffsetX}
			/>
			<SpinBox
				value={gridOffsetYMm}
				min={-maxOffsetY}
				max={maxOffsetY}
				step={0.1}
				decimals={1}
				size="sm"
				prefix="Grid dY"
				suffix="mm"
				class="w-32"
				onChange={updateGridOffsetY}
			/>
			<SpinBox
				value={app.gridConfig.overlap}
				min={0}
				max={0.5}
				step={0.01}
				decimals={2}
				size="sm"
				prefix="Overlap"
				suffix="%"
				class="w-32"
				onChange={updateGridOverlap}
			/>
		</div>

		<div class="flex items-center gap-2">
			{#if xAxis}
				<SpinBox
					bind:value={posX}
					min={xAxis.lowerLimit}
					max={xAxis.upperLimit}
					step={0.01}
					decimals={2}
					size="sm"
					prefix="X"
					suffix="mm"
					class="w-32"
					color={xAxis.isMoving ? 'var(--danger)' : undefined}
					onChange={handleXChange}
				/>
			{/if}
			{#if yAxis}
				<SpinBox
					bind:value={posY}
					min={yAxis.lowerLimit}
					max={yAxis.upperLimit}
					step={0.01}
					decimals={2}
					size="sm"
					prefix="Y"
					suffix="mm"
					class="w-32"
					color={yAxis.isMoving ? 'var(--danger)' : undefined}
					onChange={handleYChange}
				/>
			{/if}
			{#if zAxis}
				<SpinBox
					bind:value={posZ}
					min={zAxis.lowerLimit}
					max={zAxis.upperLimit}
					step={0.001}
					decimals={3}
					size="sm"
					prefix="Z"
					suffix="mm"
					class="w-32"
					color={zAxis.isMoving ? 'var(--danger)' : undefined}
					onChange={handleZChange}
				/>
			{/if}
		</div>
	</div>

	<Button
		variant={app.stageIsMoving ? 'danger' : 'outline'}
		size="sm"
		onclick={() => app.haltStage()}
		disabled={!app.stageIsMoving}
		aria-label="Halt stage"
	>
		Halt
	</Button>
</div>
