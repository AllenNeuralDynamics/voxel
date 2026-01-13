<script lang="ts">
	import Icon from '@iconify/svelte';
	import SpinBox from '$lib/ui/primitives/SpinBox.svelte';
	import SelectInput from '$lib/ui/primitives/SelectInput.svelte';
	import type { App } from '$lib/app';
	import { getStackStatusColor, type Stack, type TileOrder } from '$lib/core/types';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Tile order labels - options derived from keys
	const TILE_ORDER_LABELS: Record<TileOrder, string> = {
		row_wise: 'Row-wise',
		column_wise: 'Column-wise',
		snake_row: 'Snake (Row)',
		snake_column: 'Snake (Column)'
	};
	const TILE_ORDER_OPTIONS = Object.keys(TILE_ORDER_LABELS) as TileOrder[];

	// Computed derived state (not simple aliases)
	let gridOffsetXMm = $derived(app.gridConfig.x_offset_um / 1000);
	let gridOffsetYMm = $derived(app.gridConfig.y_offset_um / 1000);
	let maxOffsetX = $derived(app.fov.width * (1 - app.gridConfig.overlap));
	let maxOffsetY = $derived(app.fov.height * (1 - app.gridConfig.overlap));
	let stack = $derived<Stack | null>(
		app.stacks.find((s) => s.row === app.selectedTile.row && s.col === app.selectedTile.col) ?? null
	);

	// Form state
	let isEditing = $state(false);
	let zStartInput = $state(0);
	let zEndInput = $state(100);

	// Track last used Z values for smart pre-population
	let lastZStart = $state<number | null>(null);
	let lastZEnd = $state<number | null>(null);

	// Get smart default Z values: stack → last used → grid config defaults
	function getDefaultZ(): { start: number; end: number } {
		if (stack) {
			return { start: stack.z_start_um, end: stack.z_end_um };
		}
		if (lastZStart !== null && lastZEnd !== null) {
			return { start: lastZStart, end: lastZEnd };
		}
		return { start: app.gridConfig.default_z_start_um, end: app.gridConfig.default_z_end_um };
	}

	// Reset form when selected tile changes
	$effect(() => {
		// Track selectedTile to trigger on tile change
		void app.selectedTile;
		isEditing = false;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	});

	// Derived state
	let isDirty = $derived(stack ? zStartInput !== stack.z_start_um || zEndInput !== stack.z_end_um : true);
	let numSlices = $derived(Math.ceil(Math.abs(zEndInput - zStartInput) / app.gridConfig.z_step_um));
	let hasStack = $derived(stack !== null);

	// Format position for display
	function formatMm(um: number, decimals: number = 2): string {
		return (um / 1000).toFixed(decimals);
	}

	// Grid control handlers
	function updateGridOffsetX(value: number) {
		if (app.gridLocked) return;
		app.setGridOffset(value * 1000, app.gridConfig.y_offset_um);
	}

	function updateGridOffsetY(value: number) {
		if (app.gridLocked) return;
		app.setGridOffset(app.gridConfig.x_offset_um, value * 1000);
	}

	function updateGridOverlap(value: number) {
		if (app.gridLocked) return;
		app.setGridOverlap(value);
	}

	function updateTileOrder(value: string | number) {
		app.setTileOrder(value as TileOrder);
	}

	// Stack handlers
	function handleEdit() {
		isEditing = true;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	}

	function handleSubmit() {
		if (hasStack) {
			app.editStack(app.selectedTile.row, app.selectedTile.col, zStartInput, zEndInput);
		} else {
			app.addStack(app.selectedTile.row, app.selectedTile.col, zStartInput, zEndInput);
		}
		// Track last used values for smart pre-population
		lastZStart = zStartInput;
		lastZEnd = zEndInput;
		isEditing = false;
	}

	function handleDelete() {
		if (confirm('Delete this stack?')) {
			app.removeStack(app.selectedTile.row, app.selectedTile.col);
		}
	}

	function handleCancel() {
		isEditing = false;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	}

	// Z input handlers
	function updateZStart(value: number) {
		zStartInput = value;
	}

	function updateZEnd(value: number) {
		zEndInput = value;
	}

	function useCurrentZForStart() {
		zStartInput = Math.round(app.zAxis!.position * 1000);
	}

	function useCurrentZForEnd() {
		zEndInput = Math.round(app.zAxis!.position * 1000);
	}
</script>

{#snippet spinboxRow(
	label: string,
	value: number,
	onChange: (v: number) => void,
	min: number,
	max: number,
	step: number,
	decimals: number,
	unit: string
)}
	<div class="flex h-6 items-center justify-between gap-2">
		<span class="w-14 text-zinc-400">{label}</span>
		<div class="flex items-center gap-1">
			<SpinBox {value} {onChange} {min} {max} {step} {decimals} numCharacters={4} showButtons={true} align="right" />
			<span class="w-6 text-right text-zinc-400">{unit}</span>
		</div>
	</div>
{/snippet}

{#snippet staticRow(label: string, value: string, unit: string = '')}
	<div class="flex h-6 items-center justify-between gap-2 text-zinc-400">
		<span class="w-14">{label}</span>
		<div class="flex items-center gap-1">
			<span class="font-mono text-zinc-300">{value}</span>
			{#if unit}
				<span class="w-6 text-right text-zinc-400">{unit}</span>
			{/if}
		</div>
	</div>
{/snippet}

{#snippet editableZRow(
	label: string,
	inputValue: number,
	displayValue: number | null,
	onChange: (v: number) => void,
	onUseCurrent: () => void,
	min: number,
	max: number
)}
	<div class="flex h-6 items-center justify-between gap-2">
		<span class="w-14 text-zinc-400">{label}</span>
		<div class="flex flex-1 items-center justify-end gap-1">
			{#if isEditing}
				<button
					onclick={onUseCurrent}
					class="mr-2 rounded px-1 py-0.5 text-[0.6rem] text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200"
					title="Use current Z position"
				>
					Use Current Z
				</button>
				<SpinBox
					value={inputValue}
					{onChange}
					{min}
					{max}
					step={10}
					decimals={0}
					numCharacters={6}
					showButtons={false}
					align="right"
				/>
				<span class="w-6 text-right text-zinc-400">µm</span>
			{:else}
				<span class="font-mono text-zinc-300">{displayValue ?? '—'}</span>
				<span class="w-6 text-right text-zinc-400">µm</span>
			{/if}
		</div>
	</div>
{/snippet}

{#if app.zAxis}
	<div class="flex flex-col border-t border-zinc-800 bg-zinc-800/30">
		<!-- Tile & Stack Section -->
		<div class="flex flex-col gap-2 px-4 py-4">
			<!-- Header: tile label + stack action buttons -->
			<div class="flex items-center justify-between">
				<span class="font-mono text-xs font-semibold {getStackStatusColor(stack?.status ?? null)}">
					R{app.selectedTile.row}, C{app.selectedTile.col}
				</span>
				<div class="flex items-center gap-0.5">
					{#if isEditing}
						{#if hasStack}
							<button
								onclick={handleDelete}
								class="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-rose-400"
								title="Delete stack"
							>
								<Icon icon="mdi:trash-can-outline" width="14" height="14" />
							</button>
						{/if}
						{#if isDirty}
							<button
								onclick={handleSubmit}
								class="rounded p-1 text-emerald-500 transition-colors hover:bg-zinc-700 hover:text-emerald-400"
								title={hasStack ? 'Save changes' : 'Add stack'}
							>
								<Icon icon="mdi:check" width="14" height="14" />
							</button>
						{/if}
						<button
							onclick={handleCancel}
							class="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
							title="Cancel"
						>
							<Icon icon="mdi:close" width="14" height="14" />
						</button>
					{:else}
						<button
							onclick={handleEdit}
							class="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
							title={hasStack ? 'Edit stack' : 'Add stack'}
						>
							<Icon icon="mdi:pencil-outline" width="14" height="14" />
						</button>
					{/if}
				</div>
			</div>

			<!-- Content rows -->
			<div class="flex flex-col gap-2 text-[0.65rem]">
				<!-- Tile position -->
				{@render staticRow('X', formatMm(app.selectedTile.x_um), 'mm')}
				{@render staticRow('Y', formatMm(app.selectedTile.y_um), 'mm')}

				<!-- Tile size -->
				{@render staticRow('W', formatMm(app.selectedTile.w_um, 1), 'mm')}
				{@render staticRow('H', formatMm(app.selectedTile.h_um, 1), 'mm')}

				<!-- Z range -->
				{@render editableZRow(
					'Z Start',
					zStartInput,
					stack?.z_start_um ?? null,
					updateZStart,
					useCurrentZForStart,
					app.zAxis.lowerLimit * 1000,
					app.zAxis.upperLimit * 1000
				)}
				{@render editableZRow(
					'Z End',
					zEndInput,
					stack?.z_end_um ?? null,
					updateZEnd,
					useCurrentZForEnd,
					app.zAxis.lowerLimit * 1000,
					app.zAxis.upperLimit * 1000
				)}

				<!-- Derived -->
				{@render staticRow('Step', String(app.gridConfig.z_step_um), 'µm')}
				<div class="flex h-6 items-center justify-between gap-2 text-zinc-400">
					<span class="w-14">Slices</span>
					<span class="font-mono {isEditing ? 'text-zinc-200' : 'text-zinc-300'}"
						>{isEditing ? numSlices : (stack?.num_frames ?? '—')}</span
					>
				</div>

				<!-- Metadata  -->
				{@render staticRow('Profile', stack?.profile_id ?? '—')}
				<div class="flex h-6 items-center justify-between gap-2 text-zinc-400">
					<span class="w-14">Status</span>
					<span class="font-mono {getStackStatusColor(stack?.status ?? null)}">{stack?.status}</span>
				</div>
			</div>
		</div>

		<!-- Grid Settings Section -->
		<div class="flex flex-col gap-3 border-y border-zinc-700/50 px-4 py-4">
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-zinc-300">Grid</span>
				<div class="rounded p-1 {app.gridLocked ? 'text-amber-500' : 'text-zinc-500'}">
					<Icon icon={app.gridLocked ? 'mdi:lock' : 'mdi:lock-open-outline'} width="14" height="14" />
				</div>
			</div>

			<!-- Grid parameters (lockable) -->
			<div
				class="flex flex-col gap-2 text-[0.65rem]"
				class:opacity-70={app.gridLocked}
				class:pointer-events-none={app.gridLocked}
			>
				{@render spinboxRow('Offset X', gridOffsetXMm, updateGridOffsetX, -maxOffsetX, maxOffsetX, 0.1, 1, 'mm')}
				{@render spinboxRow('Offset Y', gridOffsetYMm, updateGridOffsetY, -maxOffsetY, maxOffsetY, 0.1, 1, 'mm')}
				{@render spinboxRow('Overlap', app.gridConfig.overlap, updateGridOverlap, 0, 0.5, 0.05, 2, '%')}
				{@render staticRow('Z Step', String(app.gridConfig.z_step_um), 'µm')}
			</div>

			<!-- Separator -->
			<div class="-mx-4 border-t border-zinc-700/50"></div>

			<!-- Tile order (not locked - can change anytime) -->
			<div class="flex h-6 items-center justify-between gap-2 text-[0.65rem]">
				<span class="w-14 text-zinc-400">Order</span>
				<SelectInput
					value={app.tileOrder}
					options={TILE_ORDER_OPTIONS}
					onChange={updateTileOrder}
					formatOption={(opt) => TILE_ORDER_LABELS[opt as TileOrder]}
				/>
			</div>
		</div>
	</div>
{/if}
