<script lang="ts">
	import type { Session } from '$lib/main';
	import { SpinBox } from '$lib/ui/kit';

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	let gc = $derived(session.plan.grid_configs[profileId] ?? null);
	let disabled = $derived(profileId !== session.activeProfileId || session.gridLocked);
	let gridLimX = $derived(session.fov.width * (1 - (gc?.overlap ?? 0.1)));
	let gridLimY = $derived(session.fov.height * (1 - (gc?.overlap ?? 0.1)));
</script>

{#if gc}
	<div
		class="flex items-center gap-2"
		class:opacity-70={disabled}
		class:pointer-events-none={disabled}
	>
		<SpinBox
			value={gc.x_offset_um / 1000}
			min={-gridLimX}
			max={gridLimX}
			step={0.1}
			snapValue={0.0}
			decimals={1}
			numCharacters={6}
			size="md"
			prefix="dX"
			suffix="mm"
			onChange={(value: number) => {
				if (disabled) return;
				session.setGridOffset(value * 1000, gc!.y_offset_um);
			}}
		/>
		<SpinBox
			value={gc.y_offset_um / 1000}
			min={-gridLimY}
			max={gridLimY}
			snapValue={0.0}
			step={0.1}
			decimals={1}
			numCharacters={6}
			size="md"
			prefix="dY"
			suffix="mm"
			onChange={(value: number) => {
				if (disabled) return;
				session.setGridOffset(gc!.x_offset_um, value * 1000);
			}}
		/>
		<SpinBox
			value={gc.overlap}
			min={0}
			max={0.5}
			snapValue={0.1}
			step={0.01}
			decimals={2}
			numCharacters={5}
			size="md"
			prefix="Overlap"
			onChange={(value: number) => {
				if (disabled) return;
				session.setGridOverlap(value);
			}}
		/>
	</div>
{:else}
	<p class="text-xs text-muted-foreground">No grid config for this profile</p>
{/if}
