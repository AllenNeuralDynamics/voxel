<script lang="ts">
	import Icon from '@iconify/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { App } from '$lib/app';
	import type { Tile, Stack, StackStatus } from '$lib/core/types';
	import { Select, Checkbox, SpinBox } from '$lib/ui/primitives';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Filter state
	type FilterMode = 'all' | 'with_stack' | 'without_stack';
	let filterMode = $state<FilterMode>('all');

	const filterOptions = [
		{ value: 'all' as const, label: 'All' },
		{ value: 'with_stack' as const, label: 'Stacks' },
		{ value: 'without_stack' as const, label: 'No Stacks' }
	];

	// Default Z values for new stacks (in µm)
	let defaultZStart = $state(0);
	let defaultZEnd = $state(500);

	// Checked items for bulk operations (separate from focused tile)
	let checkedItems = new SvelteSet<string>();

	// Helper to create tile key
	function tileKey(row: number, col: number): string {
		return `${row},${col}`;
	}

	// Get stack for a tile
	function getStack(tile: Tile): Stack | null {
		return app.stacks.find((s) => s.row === tile.row && s.col === tile.col) ?? null;
	}

	// Filtered tiles
	const filteredTiles = $derived.by(() => {
		switch (filterMode) {
			case 'with_stack':
				return app.tiles.filter((t) => getStack(t) !== null);
			case 'without_stack':
				return app.tiles.filter((t) => getStack(t) === null);
			default:
				return app.tiles;
		}
	});

	// Count of checked items (only count those that are visible after filter)
	const checkedCount = $derived.by(() => {
		const visibleKeys = new Set(filteredTiles.map((t) => tileKey(t.row, t.col)));
		return Array.from(checkedItems).filter((key) => visibleKeys.has(key)).length;
	});

	// Select all checkbox state
	const allChecked = $derived(filteredTiles.length > 0 && checkedCount === filteredTiles.length);
	const someChecked = $derived(checkedCount > 0 && checkedCount < filteredTiles.length);

	// Handle select all toggle
	function handleSelectAll(checked: boolean) {
		if (checked) {
			// Select all filtered tiles
			for (const tile of filteredTiles) {
				checkedItems.add(tileKey(tile.row, tile.col));
			}
		} else {
			// Deselect all filtered tiles
			for (const tile of filteredTiles) {
				checkedItems.delete(tileKey(tile.row, tile.col));
			}
		}
	}

	// Check if a tile row is the focused tile
	function isFocused(tile: Tile): boolean {
		return app.selectedTile.row === tile.row && app.selectedTile.col === tile.col;
	}

	// Handle row click (sets focused tile, syncs with GridCanvas)
	function handleRowClick(tile: Tile) {
		app.selectTile(tile.row, tile.col);
	}

	// Handle checkbox toggle
	function handleCheckboxChange(tile: Tile, checked: boolean) {
		const key = tileKey(tile.row, tile.col);
		if (checked) {
			checkedItems.add(key);
		} else {
			checkedItems.delete(key);
		}
		handleRowClick(tile);
	}

	// Check if tile is checked
	function isChecked(tile: Tile): boolean {
		return checkedItems.has(tileKey(tile.row, tile.col));
	}

	// Add stack to tile
	function handleAddStack(tile: Tile) {
		app.addStack(tile.row, tile.col, defaultZStart, defaultZEnd);
		handleRowClick(tile);
	}

	// Handle double-click on tile to move stage
	function handleTileDoubleClick(tile: Tile) {
		handleRowClick(tile);
		app.moveToGridCell(tile.row, tile.col);
	}

	// Delete selected stacks
	function handleDeleteSelected() {
		const positions = Array.from(checkedItems)
			.map((key) => {
				const [row, col] = key.split(',').map(Number);
				return { row, col };
			})
			.filter(({ row, col }) => {
				// Only delete if has stack
				return app.stacks.some((s) => s.row === row && s.col === col);
			});

		if (positions.length > 0) {
			app.removeStacks(positions);
		}
		checkedItems.clear();
	}

	// Clear all stacks with confirmation
	function handleClearAll() {
		if (app.stacks.length === 0) return;
		if (confirm(`Delete all ${app.stacks.length} stacks?`)) {
			app.clearAllStacks();
		}
	}

	// Handle Z range change - applies to all checked items with stacks
	function handleZChange(tile: Tile, zStart: number, zEnd: number) {
		handleRowClick(tile);
		const key = tileKey(tile.row, tile.col);

		// Get all checked tiles that have stacks
		const checkedWithStacks = Array.from(checkedItems)
			.map((k) => {
				const [row, col] = k.split(',').map(Number);
				return { row, col };
			})
			.filter(({ row, col }) => app.stacks.some((s) => s.row === row && s.col === col));

		// If this tile is checked and there are other checked tiles with stacks, bulk edit
		if (checkedItems.has(key) && checkedWithStacks.length > 1) {
			app.editStacks(checkedWithStacks, zStart, zEnd);
		} else {
			// Single edit
			app.editStack(tile.row, tile.col, zStart, zEnd);
		}
	}

	// Status color classes
	const statusColors: Record<StackStatus, string> = {
		planned: 'text-blue-400',
		acquiring: 'text-cyan-400',
		completed: 'text-emerald-400',
		failed: 'text-rose-400',
		skipped: 'text-zinc-500'
	};
</script>

<div class="flex h-full flex-col text-xs text-zinc-300">
	<!-- Table -->
	<div class="flex-1 overflow-auto">
		<table class="w-full border-collapse">
			<thead class="sticky top-0 z-10 bg-zinc-900">
				<tr>
					<th class="w-8 border-b border-zinc-700 px-5 py-1.5">
						<div class="flex items-center justify-center">
							<Checkbox checked={allChecked} indeterminate={someChecked} onchange={handleSelectAll} size="sm" />
						</div>
					</th>
					<th class="w-26 border-b border-zinc-700 p-1.5 text-left">
						<Select bind:value={filterMode} options={filterOptions} size="sm" />
					</th>
					<th
						class="w-32 border-b border-zinc-700 p-2 text-left text-[0.65rem] font-medium tracking-wider text-zinc-300 uppercase"
					>
						Position
					</th>
					<th
						class="w-24 border-b border-zinc-700 p-2 text-left text-[0.65rem] font-medium tracking-wider text-zinc-300 uppercase"
					>
						<div class="flex items-center gap-1.5">
							<span>Stacks</span>
							<button
								class="rounded p-0.5 text-zinc-300 transition-colors hover:bg-zinc-700 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-40"
								onclick={handleClearAll}
								disabled={app.stacks.length === 0}
								title="Clear all stacks"
							>
								<Icon icon="mdi:delete-outline" width="14" height="14" />
							</button>
						</div>
					</th>
					<th class="w-56 border-b border-zinc-700 p-1.5 text-left">
						<div class="flex items-center gap-1">
							<SpinBox bind:value={defaultZStart} min={0} step={10} numCharacters={12} showButtons={false} />
							<span class="text-zinc-500">→</span>
							<SpinBox
								bind:value={defaultZEnd}
								min={0}
								step={10}
								numCharacters={12}
								showButtons={false}
								align="right"
							/>
							<span class="ml-3 text-[0.65rem] text-zinc-400">µm</span>
						</div>
					</th>
					<th class="min-w-40 border-b border-zinc-700 p-1.5 pr-5 text-left"></th>
				</tr>
			</thead>
			<tbody>
				{#each filteredTiles as tile (tileKey(tile.row, tile.col))}
					{@const stack = getStack(tile)}
					{@const focused = isFocused(tile)}
					<tr
						class="cursor-pointer border-b border-zinc-800 border-l-2 border-l-transparent transition-[background-color] hover:bg-zinc-800"
						class:!border-l-amber-500={focused}
						onclick={() => handleRowClick(tile)}
					>
						<td class="p-1.5 px-5">
							<div class="flex items-center justify-center">
								<Checkbox
									checked={isChecked(tile)}
									onchange={(checked: boolean) => handleCheckboxChange(tile, checked)}
									size="sm"
								/>
							</div>
						</td>
						<td class="p-1.5 px-3 text-left font-mono" ondblclick={() => handleTileDoubleClick(tile)}>
							R{tile.row}, C{tile.col}
						</td>
						<td class="p-1.5 font-mono text-[0.65rem] text-zinc-400">
							{(tile.x_um / 1000).toFixed(2)}, {(tile.y_um / 1000).toFixed(2)} mm
						</td>
						<td class="p-1.5">
							{#if stack}
								<span class={statusColors[stack.status]}>{stack.status}</span>
							{:else}
								<button
									class="inline-flex items-center gap-1 rounded border border-zinc-700 bg-transparent px-1.5 py-0.5 text-[0.65rem] text-zinc-400 transition-colors hover:border-emerald-500 hover:text-emerald-500"
									onclick={() => handleAddStack(tile)}
								>
									<Icon icon="mdi:plus" width="12" height="12" />
									Add
								</button>
							{/if}
						</td>
						<td class="p-1.5" onclick={() => handleRowClick(tile)}>
							{#if stack}
								<div class="flex items-center gap-1">
									<SpinBox
										value={stack.z_start_um}
										min={0}
										step={100}
										numCharacters={5}
										showButtons={true}
										onChange={(v) => handleZChange(tile, v, stack.z_end_um)}
									/>
									<span class="text-zinc-600">→</span>
									<SpinBox
										value={stack.z_end_um}
										min={0}
										step={100}
										numCharacters={5}
										showButtons={true}
										onChange={(v) => handleZChange(tile, stack.z_start_um, v)}
										align="right"
									/>
									<span class="ml-3 text-[0.65rem] text-zinc-400">µm</span>
								</div>
							{:else}
								<span class="text-zinc-700">—</span>
							{/if}
						</td>
						<td class="p-1.5 pr-5"></td>
					</tr>
				{/each}
			</tbody>
		</table>

		{#if filteredTiles.length === 0}
			<div class="flex items-center justify-center p-8 text-zinc-600">
				{#if app.tiles.length === 0}
					No tiles in grid
				{:else}
					No tiles match filter
				{/if}
			</div>
		{/if}
	</div>

	<!-- Toolbar (only shown when items selected) -->
	{#if checkedCount > 0}
		<div class="flex items-center justify-end gap-3 border-t border-zinc-700 bg-zinc-900 p-2">
			<span class="text-[0.65rem] text-zinc-400">{checkedCount} selected</span>
			<button
				class="rounded border border-red-500 bg-transparent px-2 py-1 text-[0.65rem] text-red-500 transition-colors hover:bg-red-500 hover:text-white"
				onclick={handleDeleteSelected}
			>
				Delete
			</button>
		</div>
	{/if}
</div>
