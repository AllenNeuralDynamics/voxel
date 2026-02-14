<script lang="ts">
	import { Button, SpinBox } from '$lib/ui/primitives';
	import type { Axis } from '$lib/app';

	interface Props {
		xAxis: Axis;
		yAxis: Axis;
		zAxis: Axis;
	}

	let { xAxis, yAxis, zAxis }: Props = $props();

	let stageIsMoving = $derived(xAxis.isMoving || yAxis.isMoving || zAxis.isMoving);

	let posX = $derived.by(() => xAxis.position);
	let posY = $derived.by(() => yAxis.position);
	let posZ = $derived.by(() => zAxis.position);
</script>

<div class="flex items-center justify-between gap-2 font-mono text-[0.65rem]">
	<div class="flex items-center gap-2">
		<SpinBox
			value={posX}
			min={xAxis.lowerLimit}
			max={xAxis.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="sm"
			prefix="X"
			suffix="mm"
			color={xAxis.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => xAxis.move(v)}
		/>
		<SpinBox
			value={posY}
			min={yAxis.lowerLimit}
			max={yAxis.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="sm"
			prefix="Y"
			suffix="mm"
			color={yAxis.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => yAxis.move(v)}
		/>
		<SpinBox
			value={posZ}
			min={zAxis.lowerLimit}
			max={zAxis.upperLimit}
			step={0.001}
			decimals={3}
			numCharacters={8}
			size="sm"
			prefix="Z"
			suffix="mm"
			color={zAxis.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => zAxis.move(v)}
		/>
	</div>
	<Button
		variant={stageIsMoving ? 'danger' : 'outline'}
		size="sm"
		onclick={() => Promise.all([xAxis.halt(), yAxis.halt(), zAxis.halt()])}
		disabled={!stageIsMoving}
		aria-label="Halt stage"
	>
		Halt
	</Button>
</div>
