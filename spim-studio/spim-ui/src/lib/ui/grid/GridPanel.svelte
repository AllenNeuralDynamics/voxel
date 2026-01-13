<script lang="ts">
	import Icon from '@iconify/svelte';
	import SpinBox from '$lib/ui/primitives/SpinBox.svelte';
	import type { App } from '$lib/app';
	import type { Tile, Stack, StackStatus } from '$lib/core/types';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get stage and config from app
	let stage = $derived(app.stage);
	let gridConfig = $derived(app.gridConfig);
	let gridLocked = $derived(app.gridLocked);
	let layerVisibility = $derived(app.layerVisibility);

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

	// Toggle layer visibility
	function toggleGrid() {
		app.layerVisibility = { ...layerVisibility, grid: !layerVisibility.grid };
	}

	function toggleStacks() {
		app.layerVisibility = { ...layerVisibility, stacks: !layerVisibility.stacks };
	}

	function toggleFov() {
		app.layerVisibility = { ...layerVisibility, fov: !layerVisibility.fov };
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

	// Status styling
	function getStatusColor(status: StackStatus): string {
		switch (status) {
			case 'planned':
				return 'text-blue-400';
			case 'committed':
				return 'text-amber-400';
			case 'acquiring':
				return 'text-cyan-400';
			case 'completed':
				return 'text-emerald-400';
			case 'failed':
				return 'text-rose-400';
			case 'skipped':
				return 'text-zinc-500';
			default:
				return 'text-zinc-400';
		}
	}
</script>

{#if stage}
	<div class="flex flex-col border-t border-zinc-800 bg-zinc-800/30">
		<!-- Grid Settings Section -->
		<div class="flex flex-col gap-3 px-4 py-4">
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-zinc-300">Grid</span>
				{#if gridLocked}
					<span class="text-[0.65rem] text-amber-500">Locked</span>
				{/if}
			</div>

			<!-- Layer visibility toggles -->
			<div class="flex items-center justify-between text-[0.65rem] text-zinc-400">
				<span class="text-zinc-500">Layers</span>
				<label class="flex cursor-pointer items-center gap-1.5">
					<input
						type="checkbox"
						checked={layerVisibility.grid}
						onchange={toggleGrid}
						class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
					/>
					<span>Grid</span>
				</label>
				<label class="flex cursor-pointer items-center gap-1.5">
					<input
						type="checkbox"
						checked={layerVisibility.stacks}
						onchange={toggleStacks}
						class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
					/>
					<span>Stacks</span>
				</label>
				<label class="flex cursor-pointer items-center gap-1.5">
					<input
						type="checkbox"
						checked={layerVisibility.fov}
						onchange={toggleFov}
						class="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
					/>
					<span>FOV</span>
				</label>
			</div>

			<!-- Grid parameters -->
			<div
				class="grid grid-cols-2 gap-x-6 gap-y-2 text-[0.65rem]"
				class:opacity-50={gridLocked}
				class:pointer-events-none={gridLocked}
			>
				<div class="flex items-center justify-between gap-2">
					<span class="text-zinc-500">Offset X</span>
					<div class="flex items-center gap-1">
						<SpinBox
							value={gridOffsetXMm}
							onChange={updateGridOffsetX}
							min={0}
							max={stage.width}
							step={0.1}
							decimals={1}
							numCharacters={4}
							showButtons={true}
						/>
						<span class="text-zinc-600">mm</span>
					</div>
				</div>
				<div class="flex items-center justify-between gap-2">
					<span class="text-zinc-500">Offset Y</span>
					<div class="flex items-center gap-1">
						<SpinBox
							value={gridOffsetYMm}
							onChange={updateGridOffsetY}
							min={0}
							max={stage.height}
							step={0.1}
							decimals={1}
							numCharacters={4}
							showButtons={true}
						/>
						<span class="text-zinc-600">mm</span>
					</div>
				</div>
				<div class="flex items-center justify-between gap-2">
					<span class="text-zinc-500">Overlap</span>
					<SpinBox
						value={gridConfig.overlap}
						onChange={updateGridOverlap}
						min={0}
						max={0.5}
						step={0.05}
						decimals={2}
						numCharacters={4}
						showButtons={true}
					/>
				</div>
				<div class="flex items-center justify-between gap-2 text-zinc-500">
					<span>Z Step</span>
					<span class="font-mono text-zinc-400">{gridConfig.z_step_um} µm</span>
				</div>
			</div>
		</div>

		<!-- Tile Section -->
		<div class="flex flex-col gap-1.5 border-t border-zinc-700/50 px-4 py-4">
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-zinc-300">Tile</span>
				<span class="font-mono text-sm font-semibold text-zinc-200">R{selectedTile.row}, C{selectedTile.col}</span>
			</div>
			<div class="grid grid-cols-2 gap-x-6 gap-y-1 text-[0.65rem]">
				<div class="flex justify-between text-zinc-500">
					<span>X</span>
					<span class="font-mono text-zinc-400">{formatMm(selectedTile.x_um)} mm</span>
				</div>
				<div class="flex justify-between text-zinc-500">
					<span>Y</span>
					<span class="font-mono text-zinc-400">{formatMm(selectedTile.y_um)} mm</span>
				</div>
				<div class="flex justify-between text-zinc-500">
					<span>W</span>
					<span class="font-mono text-zinc-400">{formatMm(selectedTile.w_um, 1)} mm</span>
				</div>
				<div class="flex justify-between text-zinc-500">
					<span>H</span>
					<span class="font-mono text-zinc-400">{formatMm(selectedTile.h_um, 1)} mm</span>
				</div>
			</div>
		</div>

		<!-- Stack Section -->
		<div class="flex flex-col gap-2 border-t border-zinc-700/50 px-4 py-4">
			<!-- Header row with label and action buttons -->
			<div class="flex items-center justify-between">
				<span class="text-xs font-medium text-zinc-300">Stack</span>
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

			<!-- Stack content - unified layout with fixed row heights -->
			<div class="flex flex-col gap-2 text-[0.65rem]">
				<!-- Z Start -->
				<div class="flex h-6 items-center justify-between gap-2">
					<span class="w-14 text-zinc-500">Z Start</span>
					<div class="flex flex-1 items-center justify-end gap-1">
						{#if isEditing}
							<button
								onclick={() => (zStartInput = Math.round(stage.z.position * 1000))}
								class="py-0.375 mr-2 rounded border-0 border-zinc-700 px-1 text-[0.6rem] text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
								title="Use current Z position"
							>
								Use Current Z
							</button>
							<SpinBox
								bind:value={zStartInput}
								min={stage.z.lowerLimit * 1000}
								max={stage.z.upperLimit * 1000}
								step={10}
								decimals={0}
								numCharacters={6}
								showButtons={false}
								align="right"
							/>
							<span class="text-zinc-600">µm</span>
						{:else}
							<span class="font-mono text-zinc-400">{stack?.z_start_um ?? '—'} µm</span>
						{/if}
					</div>
				</div>

				<!-- Z End -->
				<div class="flex h-6 items-center justify-between gap-2">
					<span class="w-14 text-zinc-500">Z End</span>
					<div class="flex flex-1 items-center justify-end gap-1">
						{#if isEditing}
							<button
								onclick={() => (zEndInput = Math.round(stage.z.position * 1000))}
								class="py-0.375 mr-2 rounded border-0 border-zinc-700 px-1 text-[0.6rem] text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-300"
								title="Use current Z position"
							>
								Use Current Z
							</button>
							<SpinBox
								bind:value={zEndInput}
								min={stage.z.lowerLimit * 1000}
								max={stage.z.upperLimit * 1000}
								step={10}
								decimals={0}
								numCharacters={6}
								showButtons={false}
								align="right"
							/>
							<span class="text-zinc-600">µm</span>
						{:else}
							<span class="font-mono text-zinc-400">{stack?.z_end_um ?? '—'} µm</span>
						{/if}
					</div>
				</div>

				<!-- Step -->
				<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
					<span class="w-14">Step</span>
					<span class="font-mono text-zinc-400">{gridConfig.z_step_um} µm</span>
				</div>

				<!-- Slices -->
				<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
					<span class="w-14">Slices</span>
					<span class="font-mono {isEditing ? 'text-zinc-300' : 'text-zinc-400'}"
						>{isEditing ? numSlices : (stack?.num_frames ?? '—')}</span
					>
				</div>

				{#if hasStack}
					<!-- Profile -->
					<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
						<span class="w-14">Profile</span>
						<span class="font-mono text-zinc-400">{stack?.profile_id}</span>
					</div>

					<!-- Status -->
					<div class="flex h-6 items-center justify-between gap-2 text-zinc-500">
						<span class="w-14">Status</span>
						<span class="font-mono {getStatusColor(stack?.status ?? 'planned')}">{stack?.status}</span>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
