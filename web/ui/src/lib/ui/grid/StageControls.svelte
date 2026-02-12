<script lang="ts">
	import { Button, SpinBox } from '$lib/ui/primitives';
	import type { App } from '$lib/app';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

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

<div class="flex items-center gap-4 font-mono text-[0.65rem]">
	{#if xAxis}
		<SpinBox
			bind:value={posX}
			min={xAxis.lowerLimit}
			max={xAxis.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={6}
			size="sm"
			prefix="X"
			suffix="mm"
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
			numCharacters={6}
			size="sm"
			prefix="Y"
			suffix="mm"
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
			numCharacters={6}
			size="sm"
			prefix="Z"
			suffix="mm"
			color={zAxis.isMoving ? 'var(--danger)' : undefined}
			onChange={handleZChange}
		/>
	{/if}
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
