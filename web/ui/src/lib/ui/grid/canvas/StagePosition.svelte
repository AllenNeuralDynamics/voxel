<script lang="ts">
	import type { Session } from '$lib/main';
	import { Button, SpinBox } from '$lib/ui/primitives';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let isStageMoving = $derived(session.xAxis?.isMoving || session.yAxis?.isMoving || session.zAxis?.isMoving);
</script>

{#if session.xAxis && session.yAxis && session.zAxis}
	<div class="flex items-center gap-3">
		<div class="flex items-center gap-2">
			<SpinBox
				value={session.xAxis.position}
				min={session.xAxis.lowerLimit}
				max={session.xAxis.upperLimit}
				step={0.01}
				decimals={2}
				numCharacters={8}
				size="sm"
				prefix="X"
				suffix="mm"
				color={session.xAxis.isMoving ? 'var(--danger)' : undefined}
				onChange={(v) => session.xAxis && session.xAxis.move(v)}
			/>
			<SpinBox
				value={session.yAxis.position}
				min={session.yAxis.lowerLimit}
				max={session.yAxis.upperLimit}
				step={0.01}
				decimals={2}
				numCharacters={8}
				size="sm"
				prefix="Y"
				suffix="mm"
				color={session.yAxis.isMoving ? 'var(--danger)' : undefined}
				onChange={(v) => session.yAxis && session.yAxis.move(v)}
			/>
			<SpinBox
				value={session.zAxis.position}
				min={session.zAxis.lowerLimit}
				max={session.zAxis.upperLimit}
				step={0.001}
				decimals={3}
				numCharacters={8}
				size="sm"
				prefix="Z"
				suffix="mm"
				color={session.zAxis.isMoving ? 'var(--danger)' : undefined}
				onChange={(v) => session.zAxis && session.zAxis.move(v)}
			/>
		</div>
		<Button
			variant={isStageMoving ? 'danger' : 'outline'}
			size="xs"
			onclick={() => session.haltStage()}
			disabled={!isStageMoving}
			aria-label="Halt stage"
		>
			Halt
		</Button>
	</div>
{/if}
