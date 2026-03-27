<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { Button, Checkbox, Dialog, Select, SpinBox } from '$lib/ui/kit';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { sanitizeString } from '$lib/utils';
	import { cn } from '$lib/utils';
	import {
		TrashCanOutline,
		Plus,
		Restore,
		LucideCircle,
		Check,
		AlertCircleOutline,
		Minus,
		DotsSpinner
	} from '$lib/icons';
	import { watch, ElementSize } from 'runed';
	import type { Tile, Stack, StackStatus } from '$lib/main/types';

	const session = getSessionContext();

	// --- Filter ---

	type TileFilter = 'all' | 'with_stacks' | 'without_stacks' | StackStatus;
	let filter = $state<TileFilter>('all');

	const filterOptions: { value: TileFilter; label: string }[] = [
		{ value: 'all', label: 'All Tiles' },
		{ value: 'with_stacks', label: 'With Stacks' },
		{ value: 'without_stacks', label: 'Without Stacks' },
		{ value: 'planned', label: 'Planned' },
		{ value: 'completed', label: 'Completed' },
		{ value: 'failed', label: 'Failed' },
		{ value: 'skipped', label: 'Skipped' }
	];

	// --- Derived data ---

	const stackMap = $derived(new Map(session.activeStacks.map((s) => [`${s.row},${s.col}`, s])));

	const filteredTiles = $derived.by(() => {
		return session.tiles.filter((t) => {
			const stack = stackMap.get(`${t.row},${t.col}`);
			switch (filter) {
				case 'all':
					return true;
				case 'with_stacks':
					return !!stack;
				case 'without_stacks':
					return !stack;
				default:
					return stack?.status === filter;
			}
		});
	});

	const selectedStacks = $derived(session.activeStacks.filter((s) => session.isTileSelected(s.row, s.col)));

	const selectedEmptyCount = $derived(session.selectedTiles.filter((t) => !stackMap.has(`${t.row},${t.col}`)).length);

	const hasSelection = $derived(session.selectedTiles.length > 0);

	// Acquisition order: index of each stack in the plan's ordered stacks list
	const acquisitionOrder = $derived(
		new Map(session.stacks.map((s, i) => [`${s.profile_id}:${s.row},${s.col}`, i + 1]))
	);

	// --- Merged Z values for batch editing ---

	function commonValue(values: number[]): number | undefined {
		if (values.length === 0) return undefined;
		const first = values[0];
		return values.every((v) => v === first) ? first : undefined;
	}

	const commonZStart = $derived(commonValue(selectedStacks.map((s) => s.z_start_um)));
	const commonZEnd = $derived(commonValue(selectedStacks.map((s) => s.z_end_um)));
	const commonZStep = $derived(commonValue(selectedStacks.map((s) => s.z_step_um)));
	const totalFrames = $derived(selectedStacks.reduce((sum, s) => sum + s.num_frames, 0));
	const totalRange = $derived(selectedStacks.reduce((sum, s) => sum + Math.abs(s.z_end_um - s.z_start_um), 0));

	// --- Actions ---

	function applyZRange(field: 'zStartUm' | 'zEndUm', value: number) {
		if (selectedStacks.length === 0) return;
		session.editStacks(
			selectedStacks.map((s) => ({
				row: s.row,
				col: s.col,
				zStartUm: field === 'zStartUm' ? value : s.z_start_um,
				zEndUm: field === 'zEndUm' ? value : s.z_end_um
			}))
		);
	}

	function addStacksForEmpty() {
		const gc = session.gridConfig;
		if (!gc) return;
		const emptySelected = session.selectedTiles.filter((t) => !stackMap.has(`${t.row},${t.col}`));
		if (emptySelected.length === 0) return;
		session.addStacks(
			emptySelected.map((t) => ({
				row: t.row,
				col: t.col,
				zStartUm: gc.default_z_start_um,
				zEndUm: gc.default_z_end_um
			}))
		);
	}

	function addSingleStack(tile: Tile) {
		const gc = session.gridConfig;
		if (!gc) return;
		session.addStacks([
			{
				row: tile.row,
				col: tile.col,
				zStartUm: gc.default_z_start_um,
				zEndUm: gc.default_z_end_um
			}
		]);
	}

	function removeSelectedStacks() {
		if (selectedStacks.length === 0) return;
		session.removeStacks(selectedStacks.map((s) => ({ row: s.row, col: s.col })));
		clearDialogOpen = false;
	}

	// --- Selection ---

	let lastClickedIndex = $state<number>(-1);

	function handleRowClick(tile: Tile, index: number, e: MouseEvent) {
		const pos: [number, number] = [tile.row, tile.col];
		if (e.metaKey || e.ctrlKey) {
			if (session.isTileSelected(tile.row, tile.col)) {
				session.removeFromSelection([pos]);
			} else {
				session.addToSelection([pos]);
			}
		} else if (e.shiftKey && lastClickedIndex >= 0) {
			const from = Math.min(lastClickedIndex, index);
			const to = Math.max(lastClickedIndex, index);
			const range = filteredTiles.slice(from, to + 1).map((t): [number, number] => [t.row, t.col]);
			session.selectTiles(range);
		} else {
			session.selectTiles([pos]);
		}
		lastClickedIndex = index;
	}

	function toggleTile(tile: Tile) {
		const pos: [number, number] = [tile.row, tile.col];
		if (session.isTileSelected(tile.row, tile.col)) {
			session.removeFromSelection([pos]);
		} else {
			session.addToSelection([pos]);
		}
	}

	// --- Auto-scroll to selection from canvas ---

	watch(
		() => session.selectedTiles[0],
		(first) => {
			if (!first) return;
			const el = document.getElementById(`tile-${first.row}-${first.col}`);
			el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
		}
	);

	// --- Clear dialog ---

	let clearDialogOpen = $state(false);
	let clearMode = $state<'selected' | 'all'>('selected');

	// --- Profile info ---

	const activeProfile = $derived(session.config.profiles[session.activeProfileId ?? '']);

	const activeProfileLabel = $derived(
		session.activeProfileId ? (activeProfile?.label ?? sanitizeString(session.activeProfileId)) : ''
	);

	const stackCount = $derived(session.activeStacks.length);

	// --- Pane sizing (pixel-based min for sidebar) ---

	const SIDEBAR_MIN_PX = 300;
	let paneGroupEl = $state<HTMLElement | null>(null);
	const paneGroupSize = new ElementSize(() => paneGroupEl);
</script>

{#snippet statusIcon(status: StackStatus | undefined)}
	{#if status === 'acquiring'}
		<DotsSpinner width="12" height="12" class="text-(--stack-status)" />
	{:else if status === 'completed'}
		<Check width="12" height="12" class="text-(--stack-status)" />
	{:else if status === 'failed'}
		<AlertCircleOutline width="12" height="12" class="text-(--stack-status)" />
	{:else if status === 'skipped'}
		<Minus width="12" height="12" class="text-(--stack-status)" />
	{:else if status === 'planned'}
		<LucideCircle width="12" height="12" class="text-(--stack-status)" />
	{:else}
		<Plus width="12" height="12" />
	{/if}
{/snippet}

{#snippet tileRow(tile: Tile, stack: Stack | undefined, selected: boolean, index: number)}
	<div
		id="tile-{tile.row}-{tile.col}"
		role="row"
		tabindex="0"
		aria-selected={selected}
		aria-label="Tile R{tile.row} C{tile.col}{stack ? `, ${stack.status}` : ', empty'}"
		data-stack-status={stack?.status ?? ''}
		class={cn(
			'col-span-full grid cursor-default grid-cols-subgrid items-center gap-x-3 px-3 py-1.5 text-left text-xs transition-colors',
			'border-b border-border/50 last:border-b-0',
			selected ? 'bg-element-selected' : 'hover:bg-element-hover'
		)}
		onclick={(e) => handleRowClick(tile, index, e)}
		onkeydown={(e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				handleRowClick(tile, index, e as unknown as MouseEvent);
			}
		}}
	>
		<!-- Checkbox -->
		<Checkbox checked={selected} size="sm" onchange={() => toggleTile(tile)} />

		<!-- Grid position -->
		<span class="pr-2 text-fg-muted tabular-nums">R{tile.row}, C{tile.col}</span>

		<!-- Stage X -->
		<span class="text-fg-muted tabular-nums">{(tile.x_um / 1000).toFixed(4)}</span>
		<!-- Stage Y -->
		<span class="text-fg-muted tabular-nums">{(tile.y_um / 1000).toFixed(4)}</span>

		<!-- Z range -->
		<div class="pr-1">
			{#if stack}
				<span class="text-fg tabular-nums">
					{stack.z_start_um.toFixed(0)} → {stack.z_end_um.toFixed(0)} µm
				</span>
			{:else}
				<span class="text-fg-faint">—</span>
			{/if}
		</div>

		<!-- Frame count -->
		<div class="pr-2">
			{#if stack}
				<span class="text-fg-muted tabular-nums">{stack.num_frames} frames</span>
			{:else}
				<span></span>
			{/if}
		</div>

		<!-- Acquisition order -->
		{#if stack}
			{@const order = acquisitionOrder.get(`${stack.profile_id}:${stack.row},${stack.col}`)}
			<span class="justify-self-end text-fg-faint tabular-nums">#{order ?? '?'}</span>
		{:else}
			<span></span>
		{/if}

		<!-- Status / Action -->
		<button
			class={cn(
				'flex items-center justify-self-end border-0 bg-transparent p-0',
				stack ? 'pointer-events-none' : 'cursor-pointer text-fg-muted transition-colors hover:text-fg'
			)}
			aria-label={stack ? stack.status : `Add stack to tile R${tile.row} C${tile.col}`}
			tabindex={stack ? -1 : 0}
			onclick={stack
				? undefined
				: (e: MouseEvent) => {
						e.stopPropagation();
						addSingleStack(tile);
					}}
		>
			{@render statusIcon(stack?.status)}
		</button>
	</div>
{/snippet}

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="setup-h" class="h-full">
	<!-- Tile list (main area) -->
	<Pane minSize={40}>
		<div class="flex h-full flex-col overflow-hidden">
			<!-- List header -->
			<div class="flex items-center gap-2 border-b border-border px-3 py-2">
				<div class="flex min-w-0 flex-1 items-center gap-2">
					{#if activeProfile}
						<span class="truncate text-sm text-fg">{activeProfileLabel}</span>
						<span class="text-xs text-fg-muted">
							{filteredTiles.length} tile{filteredTiles.length !== 1 ? 's' : ''}
							{#if stackCount > 0}
								· <span class="text-info">{stackCount} stack{stackCount !== 1 ? 's' : ''}</span>
							{/if}
						</span>
					{:else}
						<span class="text-sm text-fg-muted">No active profile</span>
					{/if}
				</div>
				<Button
					variant="ghost"
					size="xs"
					class="shrink-0 text-fg-muted hover:bg-danger/10 hover:text-danger"
					title="Clear all stacks for this profile"
					disabled={stackCount < 1}
					onclick={() => {
						clearMode = 'all';
						clearDialogOpen = true;
					}}
				>
					<TrashCanOutline width="14" height="14" />
					<span class="text-nowrap">Clear Stacks</span>
				</Button>
				<Select
					value={filter}
					options={filterOptions}
					onchange={(v) => (filter = v as TileFilter)}
					size="xs"
					variant="ghost"
					class="w-40 shrink-0"
				/>
			</div>

			<!-- Scrollable tile rows -->
			<div
				role="grid"
				aria-label="Tile list"
				class="grid flex-1 auto-rows-min grid-cols-[auto_auto_auto_1fr_auto_auto_auto_auto] content-start overflow-y-auto"
			>
				{#if filteredTiles.length === 0}
					<div class="col-span-full flex min-h-32 items-center justify-center p-4">
						<p class="text-sm text-fg-faint">
							{#if session.tiles.length === 0}
								No tiles — configure a grid first
							{:else}
								No tiles match filter
							{/if}
						</p>
					</div>
				{:else}
					{#each filteredTiles as tile, i (`${tile.row},${tile.col}`)}
						{@const stack = stackMap.get(`${tile.row},${tile.col}`)}
						{@const selected = session.isTileSelected(tile.row, tile.col)}
						{@render tileRow(tile, stack, selected, i)}
					{/each}
				{/if}
			</div>
		</div>
	</Pane>

	<PaneDivider direction="vertical" />

	<!-- Sidebar (right) -->
	<Pane
		defaultSize={30}
		minSize={paneGroupSize.width > 0 ? (SIDEBAR_MIN_PX / paneGroupSize.width) * 100 : 25}
		maxSize={45}
	>
		<div class="flex h-full flex-col overflow-y-auto bg-canvas">
			{#if !hasSelection}
				<div class="flex flex-1 items-center justify-center p-3">
					<p class="text-sm text-fg-faint">Select tiles to edit</p>
				</div>
			{:else}
				<!-- Sidebar header -->
				<div class="space-y-2 px-4 py-2">
					{#if selectedEmptyCount > 0}
						<div class="flex items-center justify-between">
							<span class="text-xs text-fg-muted">
								{selectedEmptyCount} empty tile{selectedEmptyCount !== 1 ? 's' : ''}
							</span>
							<Button variant="ghost" size="xs" onclick={addStacksForEmpty}>
								<Plus width="14" height="14" />
								Add Stacks
							</Button>
						</div>
					{/if}
					{#if selectedStacks.length > 0}
						<div class="flex items-center justify-between">
							<span class="text-xs text-fg-muted">
								{selectedStacks.length} Stack{selectedStacks.length !== 1 ? 's' : ''}
							</span>
							<Button
								variant="ghost"
								size="xs"
								class="text-danger/80 hover:bg-danger/10 hover:text-danger"
								onclick={() => {
									clearMode = 'selected';
									clearDialogOpen = true;
								}}
							>
								Remove
							</Button>
						</div>
					{/if}
					{#if selectedEmptyCount === 0 && selectedStacks.length === 0}
						<span class="text-xs text-fg-faint">No stacks at selected tiles</span>
					{/if}
				</div>

				<!-- Stack properties -->
				{#if selectedStacks.length > 0}
					<div class="border-y border-border px-4 pb-5">
						<!-- Z Range -->
						<div class="space-y-3">
							<div class="flex items-center justify-between py-3">
								<span class="text-xs text-fg-muted">Z Range</span>
								{#if commonZStep !== undefined}
									<span class="text-xs text-fg-muted tabular-nums">
										{commonZStep.toFixed(2)} µm per step
									</span>
								{/if}
							</div>
							<div class="grid grid-cols-[3.5rem_1fr_auto] items-center gap-x-4 gap-y-4">
								<span class="text-xs text-fg-muted">Start</span>
								<SpinBox
									value={commonZStart ?? 0}
									placeholder={commonZStart === undefined ? 'mixed' : ''}
									suffix="µm"
									size="xs"
									step={1}
									decimals={1}
									onChange={(v) => applyZRange('zStartUm', v)}
								/>
								<div class="flex items-center gap-1">
									<Button
										variant="outline"
										size="icon-xs"
										title="Reset to profile default"
										onclick={() => {
											const gc = session.gridConfig;
											if (gc) applyZRange('zStartUm', gc.default_z_start_um);
										}}
									>
										<Restore width="14" height="14" />
									</Button>
									<Button
										variant="outline"
										size="xs"
										title="Set from current Z position"
										onclick={() => applyZRange('zStartUm', session.stage.z.position * 1000)}
									>
										Match FOV
									</Button>
								</div>

								<span class="text-xs text-fg-muted">End</span>
								<SpinBox
									value={commonZEnd ?? 0}
									placeholder={commonZEnd === undefined ? 'mixed' : ''}
									suffix="µm"
									size="xs"
									step={1}
									decimals={1}
									onChange={(v) => applyZRange('zEndUm', v)}
								/>
								<div class="flex items-center gap-1">
									<Button
										variant="outline"
										size="icon-xs"
										title="Reset to profile default"
										onclick={() => {
											const gc = session.gridConfig;
											if (gc) applyZRange('zEndUm', gc.default_z_end_um);
										}}
									>
										<Restore width="14" height="14" />
									</Button>
									<Button
										variant="outline"
										size="xs"
										title="Set from current Z position"
										onclick={() => applyZRange('zEndUm', session.stage.z.position * 1000)}
									>
										Match FOV
									</Button>
								</div>
							</div>
							<div class="flex items-center justify-between gap-4 text-xs text-fg-muted tabular-nums">
								<span class="w-3.5rem text-xs text-fg-muted">Range</span>
								<p>
									<span>{(totalRange / 1000).toFixed(2)} mm</span>
									<span class="mx-2">·</span>
									<span>{totalFrames} frames</span>
								</p>
							</div>
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</Pane>
</PaneGroup>

<!-- Clear stacks confirmation -->
<Dialog.Root bind:open={clearDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>
					{clearMode === 'selected' ? 'Remove selected stacks' : 'Clear all stacks'}
				</Dialog.Title>
				<Dialog.Description>
					{#if clearMode === 'selected'}
						Remove {selectedStacks.length} selected stack{selectedStacks.length !== 1 ? 's' : ''} for
						<strong>{activeProfileLabel}</strong>?
					{:else}
						Remove all {stackCount} stack{stackCount !== 1 ? 's' : ''} for
						<strong>{activeProfileLabel}</strong>? The profile will be removed from the acquisition plan.
					{/if}
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (clearDialogOpen = false)}
					class="rounded border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
				>
					Cancel
				</button>
				<button
					onclick={() => {
						if (clearMode === 'selected') {
							removeSelectedStacks();
						} else {
							session.removeStacks(session.activeStacks.map((s) => ({ row: s.row, col: s.col })));
							clearDialogOpen = false;
						}
					}}
					class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
				>
					{clearMode === 'selected' ? 'Remove' : 'Clear All'}
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
