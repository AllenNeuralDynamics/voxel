<script lang="ts">
	import { Plus } from '$lib/icons';
	import { SvelteSet } from 'svelte/reactivity';
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type Tile, type Stack } from '$lib/main/types';
	import { Select, Checkbox, SpinBox } from '$lib/ui/primitives';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	type FilterMode = 'all' | 'with_stack' | 'without_stack';
	let filterMode = $state<FilterMode>('all');

	const filterOptions = [
		{ value: 'all' as const, label: 'All' },
		{ value: 'with_stack' as const, label: 'Stacks' },
		{ value: 'without_stack' as const, label: 'No Stacks' }
	];

	let defaultZStart = $state(0);
	let defaultZEnd = $state(500);

	let checkedItems = new SvelteSet<string>();

	function tileKey(row: number, col: number): string {
		return `${row},${col}`;
	}

	function getStack(tile: Tile): Stack | null {
		return session.stacks.find((s) => s.row === tile.row && s.col === tile.col) ?? null;
	}

	const filteredTiles = $derived.by(() => {
		switch (filterMode) {
			case 'with_stack':
				return session.tiles.filter((t) => getStack(t) !== null);
			case 'without_stack':
				return session.tiles.filter((t) => getStack(t) === null);
			default:
				return session.tiles;
		}
	});

	const checkedCount = $derived.by(() => {
		const visibleKeys = new Set(filteredTiles.map((t) => tileKey(t.row, t.col)));
		return Array.from(checkedItems).filter((key) => visibleKeys.has(key)).length;
	});

	const allChecked = $derived(filteredTiles.length > 0 && checkedCount === filteredTiles.length);
	const someChecked = $derived(checkedCount > 0 && checkedCount < filteredTiles.length);

	function handleSelectAll(checked: boolean) {
		if (checked) {
			for (const tile of filteredTiles) {
				checkedItems.add(tileKey(tile.row, tile.col));
			}
		} else {
			for (const tile of filteredTiles) {
				checkedItems.delete(tileKey(tile.row, tile.col));
			}
		}
	}

	function isFocused(tile: Tile): boolean {
		return session.isTileSelected(tile.row, tile.col);
	}

	function handleRowClick(e: MouseEvent, tile: Tile) {
		if (e.ctrlKey || e.metaKey) {
			if (session.isTileSelected(tile.row, tile.col)) session.removeFromSelection([[tile.row, tile.col]]);
			else session.addToSelection([[tile.row, tile.col]]);
		} else {
			session.selectTiles([[tile.row, tile.col]]);
		}
	}

	function handleCheckboxChange(tile: Tile, checked: boolean) {
		const key = tileKey(tile.row, tile.col);
		if (checked) {
			checkedItems.add(key);
		} else {
			checkedItems.delete(key);
		}
		session.selectTiles([[tile.row, tile.col]]);
	}

	function isChecked(tile: Tile): boolean {
		return checkedItems.has(tileKey(tile.row, tile.col));
	}

	function handleAddStack(tile: Tile) {
		session.addStacks([{ row: tile.row, col: tile.col, zStartUm: defaultZStart, zEndUm: defaultZEnd }]);
		session.selectTiles([[tile.row, tile.col]]);
	}

	function handleTileDoubleClick(tile: Tile) {
		session.selectTiles([[tile.row, tile.col]]);
		session.moveToGridCell(tile.row, tile.col);
	}

	function handleDeleteSelected() {
		const positions = Array.from(checkedItems)
			.map((key) => {
				const [row, col] = key.split(',').map(Number);
				return { row, col };
			})
			.filter(({ row, col }) => session.stacks.some((s) => s.row === row && s.col === col));

		if (positions.length > 0) {
			session.removeStacks(positions);
		}
		checkedItems.clear();
	}

	function handleZChange(tile: Tile, zStart: number, zEnd: number) {
		session.selectTiles([[tile.row, tile.col]]);
		const key = tileKey(tile.row, tile.col);

		const checkedWithStacks = Array.from(checkedItems)
			.map((k) => {
				const [row, col] = k.split(',').map(Number);
				return { row, col };
			})
			.filter(({ row, col }) => session.stacks.some((s) => s.row === row && s.col === col));

		if (checkedItems.has(key) && checkedWithStacks.length > 1) {
			session.editStacks(checkedWithStacks.map((p) => ({ ...p, zStartUm: zStart, zEndUm: zEnd })));
		} else {
			session.editStacks([{ row: tile.row, col: tile.col, zStartUm: zStart, zEndUm: zEnd }]);
		}
	}
</script>

<div class="flex h-full flex-col text-xs text-foreground">
	<!-- Table -->
	<div class="flex-1 overflow-auto">
		<table class="w-full border-collapse">
			<thead class="sticky top-0 z-1000 bg-card text-foreground uppercase">
				<tr class="text-[0.65rem] font-medium">
					<th class="w-8 border-b border-border px-5 py-1.5">
						<div class="flex items-center justify-center">
							<Checkbox checked={allChecked} indeterminate={someChecked} onchange={handleSelectAll} size="sm" />
						</div>
					</th>
					<th class="w-26 border-b border-border p-1.5 text-left capitalize">
						<Select bind:value={filterMode} options={filterOptions} size="sm" />
					</th>
					<th class="w-32 border-b border-border p-2 text-left font-medium tracking-wider"> Position </th>
					<th class="min-w-16 border-b border-border p-1.5"></th>
					<th class="w-56 border-b border-border p-1.5 text-left">
						<div class="flex items-center gap-1">
							<SpinBox bind:value={defaultZStart} min={0} step={10} numCharacters={13} showButtons={false} />
							<span class="text-muted-foreground">→</span>
							<SpinBox
								bind:value={defaultZEnd}
								min={0}
								step={10}
								numCharacters={13}
								showButtons={false}
								align="right"
							/>
							<span class="ml-1 text-[0.65rem] text-muted-foreground lowercase">µm</span>
						</div>
					</th>
					<th class="w-16 border-b border-border p-2 text-right font-medium tracking-wider"> Slices </th>
					<th class="w-20 border-b border-border p-2 text-right font-medium tracking-wider"> Profile </th>
					<th class="w-20 border-b border-border p-2 pr-4 text-right font-medium tracking-wider"> Stacks </th>
				</tr>
			</thead>
			<tbody class="bg-surface">
				{#each filteredTiles as tile (tileKey(tile.row, tile.col))}
					{@const stack = getStack(tile)}
					{@const focused = isFocused(tile)}
					<tr
						class="cursor-pointer border-b border-l-2 border-border border-l-transparent transition-[background-color] hover:bg-accent"
						class:!border-l-warning={focused}
						onclick={(e) => handleRowClick(e, tile)}
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
						<td class="p-1.5 font-mono text-[0.65rem] text-muted-foreground">
							{(tile.x_um / 1000).toFixed(2)}, {(tile.y_um / 1000).toFixed(2)} mm
						</td>
						<td class="p-1.5"></td>
						<td class="p-1.5" onclick={(e) => handleRowClick(e, tile)}>
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
									<span class="text-muted-foreground/50">→</span>
									<SpinBox
										value={stack.z_end_um}
										min={0}
										step={100}
										numCharacters={5}
										showButtons={true}
										onChange={(v) => handleZChange(tile, stack.z_start_um, v)}
										align="right"
									/>
									<span class="ml-1 text-[0.65rem] text-muted-foreground">µm</span>
								</div>
							{:else}
								<span class="text-muted-foreground/30">—</span>
							{/if}
						</td>
						<td class="p-1.5 text-right font-mono text-muted-foreground">
							{#if stack}
								{stack.num_frames}
							{:else}
								<span class="text-muted-foreground/30">—</span>
							{/if}
						</td>
						<td class="p-1.5 text-right text-muted-foreground">
							{#if stack}
								<span class="font-mono text-[0.65rem]">{stack.profile_id}</span>
							{:else}
								<span class="text-muted-foreground/30">—</span>
							{/if}
						</td>
						<td class="p-1.5 pr-4 text-right">
							{#if stack}
								<span class={getStackStatusColor(stack.status)}>{stack.status}</span>
							{:else}
								<button
									class="inline-flex items-center gap-1 rounded border border-border bg-transparent px-1.5 py-0.5 text-[0.65rem] text-muted-foreground transition-colors hover:border-success hover:text-success"
									onclick={() => handleAddStack(tile)}
								>
									Add
									<Plus width="12" height="12" />
								</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>

		{#if filteredTiles.length === 0}
			<div class="flex items-center justify-center p-8 text-muted-foreground/50">
				{#if session.tiles.length === 0}
					No tiles in grid
				{:else}
					No tiles match filter
				{/if}
			</div>
		{/if}
	</div>

	<!-- Toolbar (only shown when items selected) -->
	{#if checkedCount > 0}
		<div class="flex items-center justify-end gap-3 border-t border-border bg-background p-2">
			<span class="text-[0.65rem] text-muted-foreground">{checkedCount} selected</span>
			<button
				class="rounded border border-danger bg-transparent px-2 py-1 text-[0.65rem] text-danger transition-colors hover:bg-danger hover:text-danger-fg"
				onclick={handleDeleteSelected}
			>
				Delete
			</button>
		</div>
	{/if}
</div>
