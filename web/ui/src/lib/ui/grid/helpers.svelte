<script lang="ts" module>
	import type { GridConfig, Session } from '$lib/main';
	import { Link, LinkOff } from '$lib/icons';
	import { SpinBox } from '$lib/ui/kit';

	let offsetLinked = $state(false);
	let overlapLinked = $state(true);

	export { offsetControl, overlapControl, zDefaults };

	const size = 'xs';
	const variant = 'filled';
</script>

{#snippet overlapControl(session: Session, gc: GridConfig)}
	{@const editable = session.activeStacks.length === 0 || session.gridForceUnlocked}
	{@const min = 0}
	{@const max = 0.5}
	{@const snapValue = 0.1}
	{@const step = 0.01}
	{@const decimals = 2}
	{@const numCharacters = 6}
	{@const suffix = '%'}
	{@const align = 'right'}

	<div class="flex items-center gap-1.5">
		<SpinBox
			{size}
			{variant}
			{min}
			{max}
			{snapValue}
			{step}
			{decimals}
			{numCharacters}
			{suffix}
			{align}
			value={gc.overlap_x}
			prefix="Overlap X"
			disabled={!editable}
			onChange={(value) => {
				if (!editable) return;
				session.setGridOverlap(value, overlapLinked ? value : gc!.overlap_y);
			}}
		/>
		<button
			class="flex h-5 w-5 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
			title={overlapLinked ? 'Unlink overlap X/Y' : 'Link overlap X/Y'}
			onclick={() => {
				overlapLinked = !overlapLinked;
				if (overlapLinked && gc) {
					session.setGridOverlap(gc.overlap_x, gc.overlap_x);
				}
			}}
		>
			{#if overlapLinked}
				<Link class="h-3 w-3" />
			{:else}
				<LinkOff class="h-3 w-3" />
			{/if}
		</button>
		<SpinBox
			{size}
			{variant}
			{min}
			{max}
			{snapValue}
			{step}
			{decimals}
			{numCharacters}
			{suffix}
			{align}
			value={gc.overlap_y}
			prefix="Overlap Y"
			disabled={!editable}
			onChange={(value) => {
				if (!editable) return;
				session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value);
			}}
		/>
	</div>
{/snippet}

{#snippet offsetControl(session: Session, gc: GridConfig)}
	{@const editable = session.activeStacks.length === 0 || session.gridForceUnlocked}
	{@const gridLimX = session.fov.width * (1 - (gc?.overlap_x ?? 0.1))}
	{@const gridLimY = session.fov.height * (1 - (gc?.overlap_y ?? 0.1))}
	{@const snapValue = 0.0}
	{@const step = 0.1}
	{@const decimals = 2}
	{@const numCharacters = 6}
	{@const suffix = 'mm'}
	{@const align = 'right'}
	{@const disabled = !editable}
	<div class="flex items-center gap-1.5">
		<SpinBox
			value={gc.x_offset_um / 1000}
			min={-gridLimX}
			max={gridLimX}
			prefix="Offset X"
			{size}
			{variant}
			{step}
			{snapValue}
			{decimals}
			{numCharacters}
			{suffix}
			{align}
			{disabled}
			onChange={(value) => {
				if (!editable) return;
				const yMm = offsetLinked ? value : gc!.y_offset_um / 1000;
				session.setGridOffset(value * 1000, yMm * 1000);
			}}
		/>
		<button
			class="flex h-5 w-5 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
			title={offsetLinked ? 'Unlink offset X/Y' : 'Link offset X/Y'}
			onclick={() => {
				offsetLinked = !offsetLinked;
				if (offsetLinked && gc) {
					session.setGridOffset(gc.x_offset_um, gc.x_offset_um);
				}
			}}
		>
			{#if offsetLinked}
				<Link class="h-3 w-3" />
			{:else}
				<LinkOff class="h-3 w-3" />
			{/if}
		</button>
		<SpinBox
			value={gc.y_offset_um / 1000}
			min={-gridLimY}
			max={gridLimY}
			prefix="Offset Y"
			{size}
			{variant}
			{step}
			{snapValue}
			{decimals}
			{numCharacters}
			{suffix}
			{align}
			{disabled}
			onChange={(value) => {
				if (!editable) return;
				const xMm = offsetLinked ? value : gc!.x_offset_um / 1000;
				session.setGridOffset(xMm * 1000, value * 1000);
			}}
		/>
	</div>
{/snippet}

{#snippet zDefaults(session: Session, gc: GridConfig)}
	<div class="flex items-center gap-1.5">
		<SpinBox
			{size}
			{variant}
			value={gc.default_z_start_um}
			step={1}
			decimals={0}
			numCharacters={8}
			prefix="Z start"
			suffix="um"
			align="right"
			onChange={(value) => session.setGridZRange(value, gc!.default_z_end_um)}
		/>
		<SpinBox
			{size}
			{variant}
			value={gc.default_z_end_um}
			step={1}
			decimals={0}
			numCharacters={8}
			prefix="Z end"
			suffix="um"
			align="right"
			onChange={(value) => session.setGridZRange(gc!.default_z_start_um, value)}
		/>
	</div>
{/snippet}
