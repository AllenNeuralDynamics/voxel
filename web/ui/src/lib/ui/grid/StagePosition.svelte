<script lang="ts">
	import type { Stage } from '$lib/main';
	import { Button, SpinBox } from '$lib/ui/kit';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();
</script>

{#if stage && stage.x && stage.y && stage.z}
	{@const numCharacters = 10}
	<div class="flex items-center gap-2">
		<SpinBox
			value={stage.x.position / 1000}
			min={stage.x.lowerLimit / 1000}
			max={stage.x.upperLimit / 1000}
			step={0.01}
			decimals={2}
			{numCharacters}
			size="xs"
			prefix="X"
			suffix="mm"
			color={stage.x.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.x.move(v * 1000)}
		/>
		<SpinBox
			value={stage.y.position / 1000}
			min={stage.y.lowerLimit / 1000}
			max={stage.y.upperLimit / 1000}
			step={0.01}
			decimals={2}
			{numCharacters}
			size="xs"
			prefix="Y"
			suffix="mm"
			color={stage.y.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.y.move(v * 1000)}
		/>
		<SpinBox
			value={stage.z.position / 1000}
			min={stage.z.lowerLimit / 1000}
			max={stage.z.upperLimit / 1000}
			step={0.001}
			decimals={3}
			{numCharacters}
			size="xs"
			prefix="Z"
			suffix="mm"
			color={stage.z.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.z.move(v * 1000)}
		/>
		{#if stage.isMoving}
			<Button
				variant={stage.isMoving ? 'danger' : 'ghost'}
				size="xs"
				onclick={() => stage.halt()}
				disabled={!stage.isMoving}
				aria-label="Halt stage"
			>
				Halt Stage
			</Button>
		{/if}
	</div>
{/if}
