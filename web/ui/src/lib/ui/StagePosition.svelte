<script lang="ts">
	import type { Session } from '$lib/main';
	import { Button, SpinBox } from '$lib/ui/kit';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();
</script>

{#if session.stage.x && session.stage.y && session.stage.z}
	<div class="flex items-center gap-2">
		<SpinBox
			value={session.stage.x.position}
			min={session.stage.x.lowerLimit}
			max={session.stage.x.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="xs"
			prefix="X"
			suffix="mm"
			color={session.stage.x.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => session.stage.x.move(v)}
		/>
		<SpinBox
			value={session.stage.y.position}
			min={session.stage.y.lowerLimit}
			max={session.stage.y.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="xs"
			prefix="Y"
			suffix="mm"
			color={session.stage.y.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => session.stage.y.move(v)}
		/>
		<SpinBox
			value={session.stage.z.position}
			min={session.stage.z.lowerLimit}
			max={session.stage.z.upperLimit}
			step={0.001}
			decimals={3}
			numCharacters={8}
			size="xs"
			prefix="Z"
			suffix="mm"
			color={session.stage.z.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => session.stage.z.move(v)}
		/>
		{#if session.stage.isMoving}
			<Button
				variant={session.stage.isMoving ? 'danger' : 'ghost'}
				size="xs"
				onclick={() => session.stage.halt()}
				disabled={!session.stage.isMoving}
				aria-label="Halt stage"
			>
				Halt Stage
			</Button>
		{/if}
	</div>
{/if}
