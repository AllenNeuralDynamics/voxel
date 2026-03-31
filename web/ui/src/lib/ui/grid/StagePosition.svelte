<script lang="ts">
	import type { Stage } from '$lib/main';
	import { Button, SpinBox } from '$lib/ui/kit';
	let { stage }: { stage: Stage } = $props();
</script>

{#if stage && stage.x && stage.y && stage.z}
	{@const numCharacters = 10}
	{@const decimals = 3}
	{@const suffix = 'mm'}
	{@const size = 'xs'}
	{@const step = 0.01}
	<div class="flex items-center gap-2">
		<SpinBox
			value={stage.x.position / 1000}
			min={stage.x.lowerLimit / 1000}
			max={stage.x.upperLimit / 1000}
			{step}
			{decimals}
			{numCharacters}
			{size}
			prefix="X"
			{suffix}
			color={stage.x.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.x.move(v * 1000)}
		/>
		<SpinBox
			value={stage.y.position / 1000}
			min={stage.y.lowerLimit / 1000}
			max={stage.y.upperLimit / 1000}
			{step}
			{decimals}
			{numCharacters}
			{size}
			prefix="Y"
			{suffix}
			color={stage.y.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.y.move(v * 1000)}
		/>
		<SpinBox
			value={stage.z.position / 1000}
			min={stage.z.lowerLimit / 1000}
			max={stage.z.upperLimit / 1000}
			step={0.001}
			{decimals}
			{numCharacters}
			{size}
			prefix="Z"
			{suffix}
			color={stage.z.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.z.move(v * 1000)}
		/>
		<Button
			variant={stage.isMoving ? 'danger' : 'outline'}
			size="xs"
			onclick={() => stage.halt()}
			disabled={!stage.isMoving}
			aria-label="Halt stage"
		>
			Halt Stage
		</Button>
	</div>
{/if}
