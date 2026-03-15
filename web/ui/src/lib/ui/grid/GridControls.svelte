<script lang="ts">
	import type { Session } from '$lib/main';
	import { Link, LinkOff } from '$lib/icons';
	import { Field, SpinBox } from '$lib/ui/kit';

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	let gc = $derived(session.plan.grid_configs[profileId] ?? null);
	let disabled = $derived(profileId !== session.activeProfileId || session.gridLocked);
	let gridLimX = $derived(session.fov.width * (1 - (gc?.overlap_x ?? 0.1)));
	let gridLimY = $derived(session.fov.height * (1 - (gc?.overlap_y ?? 0.1)));

	let offsetLinked = $state(false);
	let overlapLinked = $state(true);
</script>

{#if gc}
	<div class="flex items-end gap-3" class:opacity-70={disabled} class:pointer-events-none={disabled}>
		<Field label="Offset">
			<div class="flex items-center gap-1.5">
				<SpinBox
					value={gc.x_offset_um / 1000}
					min={-gridLimX}
					max={gridLimX}
					step={0.1}
					snapValue={0.0}
					decimals={1}
					numCharacters={6}
					size="md"
					prefix="X"
					suffix="mm"
					onChange={(value: number) => {
						if (disabled) return;
						const yMm = offsetLinked ? value : gc!.y_offset_um / 1000;
						session.setGridOffset(value * 1000, yMm * 1000);
					}}
				/>
				<button
					class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-6 w-6 items-center justify-center rounded transition-colors"
					title={offsetLinked ? 'Unlink offset X/Y' : 'Link offset X/Y'}
					onclick={() => {
						offsetLinked = !offsetLinked;
						if (offsetLinked && gc) {
							session.setGridOffset(gc.x_offset_um, gc.x_offset_um);
						}
					}}
				>
					{#if offsetLinked}
						<Link class="h-3.5 w-3.5" />
					{:else}
						<LinkOff class="h-3.5 w-3.5" />
					{/if}
				</button>
				<SpinBox
					value={gc.y_offset_um / 1000}
					min={-gridLimY}
					max={gridLimY}
					snapValue={0.0}
					step={0.1}
					decimals={1}
					numCharacters={6}
					size="md"
					prefix="Y"
					suffix="mm"
					onChange={(value: number) => {
						if (disabled) return;
						const xMm = offsetLinked ? value : gc!.x_offset_um / 1000;
						session.setGridOffset(xMm * 1000, value * 1000);
					}}
				/>
			</div>
		</Field>
		<Field label="Overlap">
			<div class="flex items-center gap-1.5">
				<SpinBox
					value={gc.overlap_x}
					min={0}
					max={0.5}
					snapValue={0.1}
					step={0.01}
					decimals={2}
					numCharacters={6}
					size="md"
					prefix="X"
					onChange={(value: number) => {
						if (disabled) return;
						session.setGridOverlap(value, overlapLinked ? value : gc!.overlap_y);
					}}
				/>
				<button
					class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-6 w-6 items-center justify-center rounded transition-colors"
					title={overlapLinked ? 'Unlink overlap X/Y' : 'Link overlap X/Y'}
					onclick={() => {
						overlapLinked = !overlapLinked;
						if (overlapLinked && gc) {
							session.setGridOverlap(gc.overlap_x, gc.overlap_x);
						}
					}}
				>
					{#if overlapLinked}
						<Link class="h-3.5 w-3.5" />
					{:else}
						<LinkOff class="h-3.5 w-3.5" />
					{/if}
				</button>
				<SpinBox
					value={gc.overlap_y}
					min={0}
					max={0.5}
					snapValue={0.1}
					step={0.01}
					decimals={2}
					numCharacters={6}
					size="md"
					prefix="Y"
					onChange={(value: number) => {
						if (disabled) return;
						session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value);
					}}
				/>
			</div>
		</Field>
	</div>
{:else}
	<p class="text-fg-muted text-sm">No grid config for this profile</p>
{/if}
