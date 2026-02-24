<script lang="ts">
	import type { Session } from '$lib/main';
	import { Button, SpinBox } from '$lib/ui/primitives';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let { stage } = $derived(session);
</script>

<div class="flex items-center gap-3">
	<div class="flex items-center gap-2">
		<SpinBox
			value={stage.x.position}
			min={stage.x.lowerLimit}
			max={stage.x.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="sm"
			prefix="X"
			suffix="mm"
			color={stage.x.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.x.move(v)}
		/>
		<SpinBox
			value={stage.y.position}
			min={stage.y.lowerLimit}
			max={stage.y.upperLimit}
			step={0.01}
			decimals={2}
			numCharacters={8}
			size="sm"
			prefix="Y"
			suffix="mm"
			color={stage.y.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.y.move(v)}
		/>
		<SpinBox
			value={stage.z.position}
			min={stage.z.lowerLimit}
			max={stage.z.upperLimit}
			step={0.001}
			decimals={3}
			numCharacters={8}
			size="sm"
			prefix="Z"
			suffix="mm"
			color={stage.z.isMoving ? 'var(--danger)' : undefined}
			onChange={(v) => stage.z.move(v)}
		/>
	</div>
	<Button
		variant={stage.isMoving ? 'danger' : 'outline'}
		size="xs"
		onclick={() => stage.halt()}
		disabled={!stage.isMoving}
		aria-label="Halt stage"
	>
		Halt
	</Button>
</div>
