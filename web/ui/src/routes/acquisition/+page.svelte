<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { GripVertical, LucideCircle, DotsSpinner, Check, AlertCircleOutline, Minus } from '$lib/icons';
	import { PaneDivider, Select, SortableList } from '$lib/ui/kit';
	import MetadataPanel from '$lib/ui/MetadataPanel.svelte';
	import { sanitizeString, cn } from '$lib/utils';
	import { Pane, PaneGroup } from 'paneforge';
	import { Progress } from 'bits-ui';
	import { toast } from 'svelte-sonner';
	import { type Interleaving, type Stack, type TileOrder } from '$lib/main/types';
	import { SvelteMap } from 'svelte/reactivity';

	const session = getSessionContext();

	// ── Plan settings options ──

	const TILE_ORDER_OPTIONS: { value: TileOrder; label: string }[] = [
		{ value: 'row_wise', label: 'Row-wise' },
		{ value: 'column_wise', label: 'Column-wise' },
		{ value: 'snake_row', label: 'Snake (Row)' },
		{ value: 'snake_column', label: 'Snake (Column)' },
		{ value: 'custom', label: 'Custom' }
	];

	const INTERLEAVING_OPTIONS: { value: Interleaving; label: string }[] = [
		{ value: 'position_first', label: 'Position first' },
		{ value: 'profile_first', label: 'Profile first' }
	];

	// ── Fake acquisition simulation (prototyping) ──

	const FAKE_ACQ = true;

	function fakeStatus(index: number, total: number): string {
		const mid = Math.floor(total / 2);
		if (index < mid - 2) return 'completed';
		if (index === mid - 2) return 'failed';
		if (index === mid - 1) return 'skipped';
		if (index === mid) return 'acquiring';
		return 'planned';
	}

	function getStackStatus(stack: Stack, index: number, total: number): string {
		return FAKE_ACQ ? fakeStatus(index, total) : stack.status;
	}

	function fakeProgress(status: string): number {
		if (status === 'completed') return 100;
		if (status === 'acquiring') return 45;
		if (status === 'failed') return 60;
		return 0;
	}

	const STATUS_BAR_CLASSES: Record<string, string> = {
		planned: 'bg-info/15',
		acquiring: 'bg-success/15',
		completed: 'bg-success/15',
		failed: 'bg-danger/15',
		skipped: 'bg-warning/15'
	};

	// ── Stack summary ──

	const stackCounts = $derived.by(() => {
		const stacks = session.plan.stacks;
		let planned = 0;
		let completed = 0;
		let failed = 0;
		for (let i = 0; i < stacks.length; i++) {
			const status = getStackStatus(stacks[i], i, stacks.length);
			if (status === 'planned') planned++;
			else if (status === 'completed') completed++;
			else if (status === 'failed') failed++;
		}
		return { planned, completed, failed, total: stacks.length };
	});

	const statusMap = $derived.by(() => {
		const stacks = session.plan.stacks;
		const map = new SvelteMap<Stack, string>();
		for (let i = 0; i < stacks.length; i++) {
			map.set(stacks[i], getStackStatus(stacks[i], i, stacks.length));
		}
		return map;
	});

	function status(stack: Stack): string {
		return statusMap.get(stack) ?? stack.status;
	}

	// ── Grouped stack list ──

	interface StackGroup {
		label: string;
		stacks: Stack[];
	}

	const stackGroups = $derived.by<StackGroup[]>(() => {
		const stacks = session.plan.stacks;
		if (stacks.length === 0) return [];

		const groups: StackGroup[] = [];
		let currentKey = '';
		let currentGroup: StackGroup | null = null;

		for (const s of stacks) {
			const key = session.interleaving === 'profile_first' ? s.profile_id : `${s.row},${s.col}`;

			if (key !== currentKey) {
				currentKey = key;
				const label = session.interleaving === 'profile_first' ? sanitizeString(s.profile_id) : `R${s.row}, C${s.col}`;
				currentGroup = { label, stacks: [] };
				groups.push(currentGroup);
			}
			currentGroup!.stacks.push(s);
		}
		return groups;
	});

	const hasMultiItemGroups = $derived(stackGroups.some((g) => g.stacks.length > 1));

	// ── Profile reorder ──

	const planProfiles = $derived(session.plan.profiles);

	// ── Clipboard ──

	async function copySessionDir() {
		if (!session.info?.session_dir) return;
		try {
			await navigator.clipboard.writeText(session.info.session_dir);
			toast.success('Copied to clipboard');
		} catch {
			toast.error('Failed to copy');
		}
	}

	// ── Stack display helpers ──

	function formatZ(um: number): string {
		return um.toFixed(0);
	}

	const STATUS_ICON_CLASSES: Record<string, string> = {
		planned: 'text-info',
		acquiring: 'text-success',
		completed: 'text-success',
		failed: 'text-danger',
		skipped: 'text-warning'
	};

	const STATUS_ROW_CLASSES: Record<string, string> = {
		planned: '',
		acquiring: '',
		completed: '',
		failed: '',
		skipped: ''
	};
</script>

<PaneGroup direction="horizontal" autoSaveId="acquisition-h" class="h-full overflow-hidden">
	<!-- Left column: session info + plan config + metadata -->
	<Pane defaultSize={30} minSize={30} maxSize={40} class="p-4">
		<div class="bg-panel @container flex h-full flex-col justify-between overflow-hidden rounded-lg">
			<div class="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
				<!-- Plan settings -->
				<section>
					<h3 class="text-fg-muted/70 mb-2 text-xs font-medium tracking-wide uppercase">Stack Ordering</h3>
					<div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
						<span class="text-fg-muted">Tile Order</span>
						<Select
							value={session.tileOrder}
							options={TILE_ORDER_OPTIONS}
							onchange={(v) => session.setTileOrder(v as TileOrder)}
							size="xs"
						/>
						<span class="text-fg-muted">Interleaving</span>
						<Select
							value={session.interleaving}
							options={INTERLEAVING_OPTIONS}
							onchange={(v) => session.setInterleaving(v as Interleaving)}
							size="xs"
						/>
						{#if planProfiles.length > 1}
							<span class="text-fg-muted self-start pt-1">Profile Order</span>
							<SortableList.Root
								items={planProfiles}
								key={(p) => p.profile_id}
								onReorder={(reordered) => session.reorderProfiles(reordered.map((p) => p.profile_id))}
								class="flex flex-col gap-1"
							>
								{#snippet item(profile)}
									<SortableList.Item
										item={profile}
										class="profile-chip bg-element-bg text-fg flex items-center gap-1 rounded border border-border py-1 pr-2 pl-0.5 text-xs"
									>
										<GripVertical width="14" height="14" class="text-fg-muted/50 shrink-0" />
										{session.config.profiles[profile.profile_id]?.label ?? sanitizeString(profile.profile_id)}
									</SortableList.Item>
								{/snippet}
							</SortableList.Root>
						{/if}
					</div>
				</section>

				<!-- Metadata -->
				<MetadataPanel {session} class="mt-3" />
			</div>

			<!-- Session path (fixed footer) -->
			<div class="h-ui-xl border-t border-border px-4 py-2">
				{#if session.info?.session_dir}
					<button
						onclick={copySessionDir}
						class="text-fg-muted hover:text-fg shrink-0 cursor-pointer text-start text-xs break-all transition-colors"
						title="Click to copy path"
					>
						{session.info.session_dir}
					</button>
				{/if}
			</div>
		</div>
	</Pane>

	<PaneDivider />

	<!-- Right column: stack list -->
	<Pane class="p-4">
		<div class="flex h-full flex-col gap-4 overflow-hidden">
			<div class="flex items-baseline justify-between gap-4">
				<h3 class="text-fg-muted/70 text-xs font-medium tracking-wide uppercase">Stacks</h3>
				<span class="text-fg-muted text-xs">
					{#if stackCounts.completed > 0}
						{stackCounts.completed} done
					{/if}
					{#if stackCounts.planned > 0}
						{#if stackCounts.completed > 0}<span class="mx-0.5 text-border">·</span>{/if}
						{stackCounts.planned} planned
					{/if}
					{#if stackCounts.failed > 0}
						<span class="mx-0.5 text-border">·</span>
						<span class="text-danger">{stackCounts.failed} failed</span>
					{/if}
					{#if stackCounts.total === 0}
						No stacks
					{/if}
				</span>
			</div>

			<div class="flex-1 overflow-y-auto">
				{#if stackGroups.length === 0}
					<div class="text-fg-muted flex h-full items-center justify-center text-sm">
						No stacks configured. Add stacks in the scout step.
					</div>
				{:else if hasMultiItemGroups}
					<div class="flex flex-col gap-4">
						{#each stackGroups as group (group.label)}
							<div class="flex flex-col">
								<!-- Tab header -->
								<div
									class="h-ui-md border-fg-muted/30 bg-panel flex w-fit items-center rounded-t-lg border-x border-t px-3"
								>
									<span class="text-fg-muted truncate text-xs font-medium">{group.label}</span>
								</div>
								<!-- Stack rows -->
								<div class="border-fg-muted/30 flex flex-col overflow-hidden rounded-tr-lg rounded-b-lg border">
									{#each group.stacks as stack (`${stack.profile_id}:${stack.row},${stack.col}`)}
										<div
											class={cn(
												'h-ui-md border-fg-muted/30 relative flex items-center gap-3 overflow-hidden border-b px-3 text-xs last:border-b-0',
												STATUS_ROW_CLASSES[status(stack)] ?? ''
											)}
										>
											<span class="text-fg min-w-0 flex-1 truncate">
												{sanitizeString(stack.profile_id)}
												<span class="text-fg-muted ml-4">R{stack.row}, C{stack.col}</span>
												<span class="text-fg-muted/60 ml-4">{stack.x_um.toFixed(0)} × {stack.y_um.toFixed(0)} µm</span>
											</span>
											<span class="text-fg-muted shrink-0 font-mono">
												{formatZ(stack.z_start_um)} → {formatZ(stack.z_end_um)} µm
											</span>
											<span class="text-fg-muted shrink-0">{stack.num_frames} slices</span>
											{#if status(stack) === 'acquiring'}
												<DotsSpinner width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.acquiring)} />
											{:else if status(stack) === 'completed'}
												<Check width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.completed)} />
											{:else if status(stack) === 'failed'}
												<AlertCircleOutline width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.failed)} />
											{:else if status(stack) === 'skipped'}
												<Minus width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.skipped)} />
											{:else}
												<LucideCircle width="12" height="12" class={cn('shrink-0', STATUS_ICON_CLASSES.planned)} />
											{/if}
											<Progress.Root
												value={fakeProgress(status(stack))}
												max={100}
												class={cn('absolute inset-0 -z-10', STATUS_BAR_CLASSES[status(stack)] ?? '')}
												style="transform: scaleX({fakeProgress(status(stack)) / 100}); transform-origin: left"
											/>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="border-fg-muted/30 flex flex-col overflow-hidden rounded-lg border">
						{#each session.plan.stacks as stack (`${stack.profile_id}:${stack.row},${stack.col}`)}
							<div
								class={cn(
									'h-ui-md border-fg-muted/30 relative flex items-center gap-3 overflow-hidden border-b px-3 text-xs last:border-b-0',
									STATUS_ROW_CLASSES[status(stack)] ?? ''
								)}
							>
								<span class="text-fg min-w-0 flex-1 truncate">
									{sanitizeString(stack.profile_id)}
									<span class="text-fg-muted ml-4">R{stack.row}, C{stack.col}</span>
									<span class="text-fg-muted/60 ml-4">{stack.x_um.toFixed(0)} × {stack.y_um.toFixed(0)} µm</span>
								</span>
								<span class="text-fg-muted shrink-0 font-mono">
									{formatZ(stack.z_start_um)} → {formatZ(stack.z_end_um)} µm
								</span>
								<span class="text-fg-muted shrink-0">{stack.num_frames} slices</span>
								{#if status(stack) === 'acquiring'}
									<DotsSpinner width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.acquiring)} />
								{:else if status(stack) === 'completed'}
									<Check width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.completed)} />
								{:else if status(stack) === 'failed'}
									<AlertCircleOutline width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.failed)} />
								{:else if status(stack) === 'skipped'}
									<Minus width="14" height="14" class={cn('shrink-0', STATUS_ICON_CLASSES.skipped)} />
								{:else}
									<LucideCircle width="12" height="12" class={cn('shrink-0', STATUS_ICON_CLASSES.planned)} />
								{/if}
								<Progress.Root
									value={fakeProgress(status(stack))}
									max={100}
									class={cn('absolute inset-0 -z-10', STATUS_BAR_CLASSES[status(stack)] ?? '')}
									style="transform: scaleX({fakeProgress(status(stack)) / 100}); transform-origin: left"
								/>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</Pane>
</PaneGroup>

<style>
	/* DnD animation overrides */
	.profile-chip {
		cursor: grab;
		user-select: none;
		transition:
			transform 150ms ease,
			box-shadow 150ms ease,
			opacity 150ms ease;
	}

	:global(.profile-chip.svelte-dnd-dragging) {
		opacity: 0.4;
		transform: scale(0.95);
	}

	:global(.profile-chip.svelte-dnd-drop-target) {
		outline: none;
		box-shadow: 0 0 0 2px var(--color-info);
		transform: scale(1.05);
	}

	.profile-chip:active {
		cursor: grabbing;
	}
</style>
