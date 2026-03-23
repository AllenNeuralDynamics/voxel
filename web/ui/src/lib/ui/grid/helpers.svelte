<script lang="ts" module>
	import type { GridConfig, Session } from '$lib/main';
	import { Link, LinkOff, LockOutline, LockOpenOutline } from '$lib/icons';
	import { Dialog, SpinBox } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { watch } from 'runed';

	// ── Grid lock (per-instance composable) ──────────────────────────

	export interface GridLock {
		readonly forceUnlocked: boolean;
		readonly editable: boolean;
		unlock(): void;
		relock(): void;
	}

	export function createGridLock(getSession: () => Session): GridLock {
		let forceUnlocked = $state(false);

		watch(
			() => getSession().activeProfileId,
			() => {
				forceUnlocked = false;
			}
		);

		return {
			get forceUnlocked() {
				return forceUnlocked;
			},
			get editable() {
				return getSession().activeStacks.length === 0 || forceUnlocked;
			},
			unlock() {
				forceUnlocked = true;
			},
			relock() {
				forceUnlocked = false;
			}
		};
	}

	// ── Snippet state & exports ──────────────────────────────────────

	let lockDialogOpen = $state(false);
	let offsetLinked = $state(false);
	let overlapLinked = $state(true);

	export { offsetControl, overlapControl, zDefaults, lockIndicator };

	const size = 'sm';
	const variant = 'filled';
</script>

{#snippet overlapControl(session: Session, lock: GridLock, gc: GridConfig)}
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
			numCharacters={5}
			prefix="Overlap X"
			suffix="%"
			align="right"
			disabled={!lock.editable}
			onChange={(value) => {
				if (!lock.editable) return;
				session.setGridOverlap(value, overlapLinked ? value : gc!.overlap_y, lock.forceUnlocked);
			}}
		/>
		<button
			class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-5 w-5 items-center justify-center rounded transition-colors"
			title={overlapLinked ? 'Unlink overlap X/Y' : 'Link overlap X/Y'}
			onclick={() => {
				overlapLinked = !overlapLinked;
				if (overlapLinked && gc) {
					session.setGridOverlap(gc.overlap_x, gc.overlap_x, lock.forceUnlocked);
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
			numCharacters={5}
			prefix="Overlap Y"
			suffix="%"
			align="right"
			disabled={!lock.editable}
			onChange={(value) => {
				if (!lock.editable) return;
				session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value, lock.forceUnlocked);
			}}
		/>
	</div>
{/snippet}

{#snippet offsetControl(session: Session, lock: GridLock, gc: GridConfig)}
	{@const gridLimX = session.fov.width * (1 - (gc?.overlap_x ?? 0.1))}
	{@const gridLimY = session.fov.height * (1 - (gc?.overlap_y ?? 0.1))}
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
			align="right"
			disabled={!lock.editable}
			onChange={(value) => {
				if (!lock.editable) return;
				const yMm = offsetLinked ? value : gc!.y_offset_um / 1000;
				session.setGridOffset(value * 1000, yMm * 1000, lock.forceUnlocked);
			}}
		/>
		<button
			class="text-fg-muted hover:bg-element-hover hover:text-fg flex h-5 w-5 items-center justify-center rounded transition-colors"
			title={offsetLinked ? 'Unlink offset X/Y' : 'Link offset X/Y'}
			onclick={() => {
				offsetLinked = !offsetLinked;
				if (offsetLinked && gc) {
					session.setGridOffset(gc.x_offset_um, gc.x_offset_um, lock.forceUnlocked);
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
			align="right"
			disabled={!lock.editable}
			onChange={(value) => {
				if (!lock.editable) return;
				const xMm = offsetLinked ? value : gc!.x_offset_um / 1000;
				session.setGridOffset(xMm * 1000, value * 1000, lock.forceUnlocked);
			}}
		/>
	</div>
{/snippet}

{#snippet lockIndicator(session: Session, lock: GridLock)}
	{@const hasStacks = session.activeStacks.length > 0}
	{@const activeProfileLabel = session.activeProfileId
		? (session.config.profiles[session.activeProfileId]?.label ?? sanitizeString(session.activeProfileId))
		: null}
	{#if activeProfileLabel}
		<div class="border-info-bg flex items-center gap-4 rounded-lg border bg-info/10 px-4 py-1">
			<span
				class="h-ui-xs flex items-center rounded-lg text-xs font-medium tracking-wide text-nowrap text-info uppercase"
			>
				{activeProfileLabel}
			</span>
			{#if hasStacks}
				<button
					class="flex cursor-pointer items-center justify-center rounded transition-colors
							{lock.forceUnlocked ? 'hover:bg-element-hover text-danger' : 'hover:bg-element-hover hover:text-fg text-warning'}"
					title={lock.forceUnlocked ? 'Re-lock grid' : 'Unlock grid editing'}
					onclick={() => {
						if (lock.forceUnlocked) {
							lock.relock();
						} else {
							lockDialogOpen = true;
						}
					}}
				>
					{#if lock.forceUnlocked}
						<LockOpenOutline class="size-4" />
					{:else}
						<LockOutline class="size-4" />
					{/if}
				</button>
			{/if}
		</div>

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
							class="text-fg-muted hover:bg-element-hover hover:text-fg rounded border border-border px-3 py-1.5 text-sm transition-colors"
						>
							Cancel
						</button>
						<button
							onclick={() => {
								lock.unlock();
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
	{:else}
		<div></div>
	{/if}
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
