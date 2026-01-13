<script lang="ts">
	import Icon from '@iconify/svelte';
	import SpinBox from '$lib/ui/primitives/SpinBox.svelte';
	import type { App } from '$lib/app';
	import { getStackStatusColor, type Tile, type Stack, type StackStatus } from '$lib/core/types';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get stage and config from app
	let stage = $derived(app.stage);
	let gridConfig = $derived(app.gridConfig);
	let gridLocked = $derived(app.gridLocked);

	// Grid offset in mm for display (stored in μm)
	let gridOffsetXMm = $derived(gridConfig.x_offset_um / 1000);
	let gridOffsetYMm = $derived(gridConfig.y_offset_um / 1000);

	// Dummy data for tile/stack (will be wired to app later)
	const dummyTile: Tile = {
		tile_id: 'tile_r2_c3',
		row: 2,
		col: 3,
		x_um: 12500,
		y_um: 8200,
		w_um: 6670,
		h_um: 5001
	};

	const dummyStack: Stack | null = {
		...dummyTile,
		z_start_um: 0,
		z_end_um: 300,
		z_step_um: 2.0,
		profile_id: 'dapi_gfp',
		status: 'planned' as StackStatus,
		output_path: null,
		num_frames: 150
	};

	// Component state for tile/stack (dummy for now)
	let selectedTile = $state<Tile>(dummyTile);
	let stack = $state<Stack | null>(dummyStack);

	// Form state
	let isEditing = $state(false);
	let zStartInput = $state(stack?.z_start_um ?? 0);
	let zEndInput = $state(stack?.z_end_um ?? 100);

	// Derived state
	let isDirty = $derived(stack ? zStartInput !== stack.z_start_um || zEndInput !== stack.z_end_um : true);
	let numSlices = $derived(Math.ceil(Math.abs(zEndInput - zStartInput) / gridConfig.z_step_um));
	let hasStack = $derived(stack !== null);

	// Format position for display
	function formatMm(um: number, decimals: number = 2): string {
		return (um / 1000).toFixed(decimals);
	}

	// Grid control handlers
	function updateGridOffsetX(value: number) {
		if (gridLocked) return;
		app.setGridOffset(value * 1000, gridConfig.y_offset_um);
	}

	function updateGridOffsetY(value: number) {
		if (gridLocked) return;
		app.setGridOffset(gridConfig.x_offset_um, value * 1000);
	}

	function updateGridOverlap(value: number) {
		if (gridLocked) return;
		app.setGridOverlap(value);
	}

	// Stack handlers
	function handleEdit() {
		isEditing = true;
		zStartInput = stack?.z_start_um ?? 0;
		zEndInput = stack?.z_end_um ?? 100;
	}

	function handleSubmit() {
		if (hasStack) {
			console.log('Editing stack:', { z_start_um: zStartInput, z_end_um: zEndInput });
			// TODO: Call app.editStack(selectedTile.tile_id, zStartInput, zEndInput)
		} else {
			console.log('Adding stack:', {
				row: selectedTile.row,
				col: selectedTile.col,
				z_start_um: zStartInput,
				z_end_um: zEndInput
			});
			// TODO: Call app.addStack(selectedTile.row, selectedTile.col, zStartInput, zEndInput)
		}
		isEditing = false;
	}

	function handleDelete() {
		if (confirm('Delete this stack?')) {
			console.log('Deleting stack:', selectedTile.tile_id);
			// TODO: Call app.removeStack(selectedTile.tile_id)
		}
	}

	function handleCancel() {
		isEditing = false;
		zStartInput = stack?.z_start_um ?? 0;
		zEndInput = stack?.z_end_um ?? 100;
	}

	// Z input handlers
	function updateZStart(value: number) {
		zStartInput = value;
	}

	function updateZEnd(value: number) {
		zEndInput = value;
	}

	function useCurrentZForStart() {
		zStartInput = Math.round(stage!.z.position * 1000);
	}

	function useCurrentZForEnd() {
		zEndInput = Math.round(stage!.z.position * 1000);
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
		<span class="w-14 text-zinc-500">{label}</span>
		<div class="flex items-center gap-1">
			<SpinBox {value} {onChange} {min} {max} {step} {decimals} numCharacters={4} showButtons={true} align="right" />
			<span class="w-6 text-right text-zinc-600">{unit}</span>
		</div>
	</div>
{/snippet}

{#snippet staticRow(label: string, value: string, unit: string = '')}
	<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
		<span class="w-14">{label}</span>
		<div class="flex items-center gap-1">
			<span class="font-mono text-zinc-400">{value}</span>
			{#if unit}
				<span class="w-6 text-right text-zinc-600">{unit}</span>
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
		<span class="w-14 text-zinc-500">{label}</span>
		<div class="flex flex-1 items-center justify-end gap-1">
			{#if isEditing}
				<button
					onclick={onUseCurrent}
					class="mr-2 rounded px-1 py-0.5 text-[0.6rem] text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
					title="Use current Z position"
				>
					Use Current Z
				</button>
				<SpinBox value={inputValue} {onChange} {min} {max} step={10} decimals={0} numCharacters={6} showButtons={false} align="right" />
				<span class="w-6 text-right text-zinc-600">µm</span>
			{:else}
				<span class="font-mono text-zinc-400">{displayValue ?? '—'}</span>
				<span class="w-6 text-right text-zinc-600">µm</span>
			{/if}
		</div>
	</div>
{/snippet}

{#if stage}
	<div class="flex flex-col border-t border-zinc-800 bg-zinc-800/30">
		<!-- Tile & Stack Section -->
		<div class="flex flex-col gap-2 px-4 py-4">
			<!-- Header: tile label + stack action buttons -->
			<div class="flex items-center justify-between">
				<span class="font-mono text-xs font-semibold {getStackStatusColor(stack?.status ?? null).tw}">
					R{selectedTile.row}, C{selectedTile.col}
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
					{:else if hasStack}
						<button
							onclick={handleEdit}
							class="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
							title="Edit stack"
						>
							<Icon icon="mdi:pencil-outline" width="14" height="14" />
						</button>
					{/if}
				</div>
			</div>

			<!-- Content rows -->
			<div class="flex flex-col gap-2 text-[0.65rem]">
				<!-- Tile position -->
				{@render staticRow('X', formatMm(selectedTile.x_um), 'mm')}
				{@render staticRow('Y', formatMm(selectedTile.y_um), 'mm')}

				<!-- Tile size -->
				{@render staticRow('W', formatMm(selectedTile.w_um, 1), 'mm')}
				{@render staticRow('H', formatMm(selectedTile.h_um, 1), 'mm')}

				<!-- Z range -->
				{@render editableZRow('Z Start', zStartInput, stack?.z_start_um ?? null, updateZStart, useCurrentZForStart, stage.z.lowerLimit * 1000, stage.z.upperLimit * 1000)}
				{@render editableZRow('Z End', zEndInput, stack?.z_end_um ?? null, updateZEnd, useCurrentZForEnd, stage.z.lowerLimit * 1000, stage.z.upperLimit * 1000)}

				<!-- Derived -->
				{@render staticRow('Step', String(gridConfig.z_step_um), 'µm')}
				<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
					<span class="w-14">Slices</span>
					<span class="font-mono {isEditing ? 'text-zinc-300' : 'text-zinc-400'}"
						>{isEditing ? numSlices : (stack?.num_frames ?? '—')}</span
					>
				</div>

				<!-- Metadata (if stack exists) -->
				{#if hasStack}
					{@render staticRow('Profile', stack?.profile_id ?? '—')}
					<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
						<span class="w-14">Status</span>
						<span class="font-mono {getStackStatusColor(stack?.status ?? null).tw}">{stack?.status}</span>
					</div>
				{/if}
			</div>
		</div>

		<!-- Grid Settings Section -->
		<div class="flex flex-col gap-3 border-y border-zinc-700/50 px-4 py-4">
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-zinc-300">Grid</span>
				<div class="rounded p-1 {gridLocked ? 'text-amber-500' : 'text-zinc-500'}">
					<Icon icon={gridLocked ? 'mdi:lock' : 'mdi:lock-open-outline'} width="14" height="14" />
				</div>
			</div>

			<!-- Grid parameters -->
			<div
				class="flex flex-col gap-2 text-[0.65rem]"
				class:opacity-50={gridLocked}
				class:pointer-events-none={gridLocked}
			>
				{@render spinboxRow('Offset X', gridOffsetXMm, updateGridOffsetX, 0, stage.width, 0.1, 1, 'mm')}
				{@render spinboxRow('Offset Y', gridOffsetYMm, updateGridOffsetY, 0, stage.height, 0.1, 1, 'mm')}
				{@render spinboxRow('Overlap', gridConfig.overlap, updateGridOverlap, 0, 0.5, 0.05, 2, '%')}
				{@render staticRow('Z Step', String(gridConfig.z_step_um), 'µm')}
			</div>
		</div>
	</div>
{/if}
