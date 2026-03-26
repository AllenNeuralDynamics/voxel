<script lang="ts">
	import type { Session } from '$lib/main';
	import { Link, LinkOff, LockOutline, LockOpenOutline } from '$lib/icons';
	import { Dialog, SpinBox } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { watch } from 'runed';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let gc = $derived(session.config.profiles[session.activeProfileId ?? '']?.grid ?? null);
	let hasStacks = $derived(session.activeStacks.length > 0);
	let gridForceUnlocked = $state(false);
	let gridEditable = $derived(!hasStacks || gridForceUnlocked);
	let gridLimX = $derived(session.fov.width * (1 - (gc?.overlap_x ?? 0.1)));
	let gridLimY = $derived(session.fov.height * (1 - (gc?.overlap_y ?? 0.1)));
	let activeProfileLabel = $derived(
		session.activeProfileId
			? (session.config.profiles[session.activeProfileId]?.label ?? sanitizeString(session.activeProfileId))
			: null
	);

	// Auto re-lock when profile changes or stacks increase
	watch(
		() => session.activeProfileId,
		() => {
			gridForceUnlocked = false;
		}
	);

	let prevStackCount = $state(0);
	watch(
		() => session.activeStacks.length,
		(count) => {
			if (count > prevStackCount) gridForceUnlocked = false;
			prevStackCount = count;
		}
	);

	let lockDialogOpen = $state(false);

	let offsetLinked = $state(false);
	let overlapLinked = $state(true);
</script>

{#if gc}
	{@const size = 'xs'}
	{@const variant = 'filled'}
	<div class="flex w-full items-center justify-between gap-4">
		<div class="flex items-center gap-1.5">
			<SpinBox
				{size}
				{variant}
				value={gc.x_offset_um / 1000}
				min={-gridLimX}
				max={gridLimX}
				step={0.1}
				snapValue={0.0}
				decimals={1}
				numCharacters={8}
				prefix="Offset X"
				suffix="mm"
				disabled={!gridEditable}
				onChange={(value) => {
					if (!gridEditable) return;
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
				{size}
				{variant}
				value={gc.y_offset_um / 1000}
				min={-gridLimY}
				max={gridLimY}
				snapValue={0.0}
				step={0.1}
				decimals={1}
				numCharacters={8}
				prefix="Offset Y"
				suffix="mm"
				disabled={!gridEditable}
				onChange={(value) => {
					if (!gridEditable) return;
					const xMm = offsetLinked ? value : gc!.x_offset_um / 1000;
					session.setGridOffset(xMm * 1000, value * 1000);
				}}
			/>
		</div>
		{#if activeProfileLabel}
			<div class="flex items-center gap-4 rounded-full bg-info/10 px-4 py-1">
				<span class="rounded-full text-xs font-medium tracking-wide text-nowrap text-info uppercase">
					{activeProfileLabel}
				</span>
				{#if hasStacks}
					<button
						class="transition-colors, flex cursor-pointer items-center justify-center rounded
						{gridForceUnlocked ? 'text-danger hover:bg-element-hover' : 'text-warning hover:bg-element-hover hover:text-fg'}"
						title={gridForceUnlocked ? 'Re-lock grid' : 'Unlock grid editing'}
						onclick={() => {
							if (gridForceUnlocked) {
								gridForceUnlocked = false;
							} else {
								lockDialogOpen = true;
							}
						}}
					>
						{#if gridForceUnlocked}
							<LockOpenOutline class="size-4" />
						{:else}
							<LockOutline class="size-4" />
						{/if}
					</button>
				{/if}
			</div>
		{/if}
		<div class="flex items-center gap-1.5">
			<SpinBox
				{size}
				{variant}
				value={gc.overlap_x}
				min={0}
				max={0.5}
				snapValue={0.1}
				step={0.01}
				decimals={2}
				numCharacters={8}
				prefix="Overlap X"
				suffix="%"
				disabled={!gridEditable}
				onChange={(value) => {
					if (!gridEditable) return;
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
				value={gc.overlap_y}
				min={0}
				max={0.5}
				snapValue={0.1}
				step={0.01}
				decimals={2}
				numCharacters={8}
				prefix="Overlap Y"
				suffix="%"
				disabled={!gridEditable}
				onChange={(value) => {
					if (!gridEditable) return;
					session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value);
				}}
			/>
		</div>
	</div>
{/if}

<Dialog.Root bind:open={lockDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Unlock grid editing</Dialog.Title>
				<Dialog.Description>
					Stacks exist for this profile. Changing grid offset or overlap will recalculate stack positions. Continue?
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (lockDialogOpen = false)}
					class="rounded border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
				>
					Cancel
				</button>
				<button
					onclick={() => {
						gridForceUnlocked = true;
						lockDialogOpen = false;
					}}
					class="rounded bg-warning px-3 py-1.5 text-sm text-warning-fg transition-colors hover:bg-warning/90"
				>
					Unlock
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
