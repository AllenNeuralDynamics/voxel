<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { GripVertical, LucideCircle, DotsSpinner, Check, AlertCircleOutline, Minus } from '$lib/icons';
	import { PaneDivider, Select, SortableList } from '$lib/ui/kit';
	import MetadataPanel from '$lib/ui/MetadataPanel.svelte';
	import { sanitizeString } from '$lib/utils';
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

	const planProfiles = $derived(session.plan.profile_order.map((id) => ({ profile_id: id })));

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
</script>

<PaneGroup direction="horizontal" autoSaveId="acquisition-h" class="h-full overflow-hidden">
	<!-- Left column: session info + plan config + metadata -->
	<Pane defaultSize={30} minSize={25} maxSize={50}>
		<div class="@container flex h-full flex-col justify-between overflow-hidden rounded-lg bg-canvas">
			<div class="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
				<!-- Plan settings -->
				<section>
					<h3 class="mb-2 text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Stack Ordering</h3>
					<div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
						<span class="text-fg-muted">Tile Order</span>
						<Select
							value={session.tileOrder}
							options={TILE_ORDER_OPTIONS}
							onchange={(v) => session.setTileOrder(v as TileOrder)}
							size="xs"
						/>
						{#if planProfiles.length > 1}
							<span class="text-fg-muted">Interleaving</span>
							<Select
								value={session.interleaving}
								options={INTERLEAVING_OPTIONS}
								onchange={(v) => session.setInterleaving(v as Interleaving)}
								size="xs"
							/>
							<span class="self-start pt-1 text-fg-muted">Profile Order</span>
							<SortableList.Root
								items={planProfiles}
								key={(p) => p.profile_id}
								onReorder={(reordered) => session.reorderProfiles(reordered.map((p) => p.profile_id))}
								class="flex flex-col gap-1"
							>
								{#snippet item(profile)}
									<SortableList.Item
										item={profile}
										class="profile-chip flex items-center gap-1 rounded border border-border bg-element-bg py-1 pr-2 pl-0.5 text-xs text-fg"
									>
										<GripVertical width="14" height="14" class="shrink-0 text-fg-muted/50" />
										{session.config.profiles[profile.profile_id]?.label ?? sanitizeString(profile.profile_id)}
									</SortableList.Item>
								{/snippet}
							</SortableList.Root>
						{/if}
					</div>
				</section>

				<!-- Metadata -->
				<MetadataPanel {session} />
			</div>

			<!-- Session path (fixed footer) -->
			<div class="h-ui-xl border-t border-border px-4 py-2">
				{#if session.info?.session_dir}
					<button
						onclick={copySessionDir}
						class="shrink-0 cursor-pointer text-start text-xs break-all text-fg-muted transition-colors hover:text-fg"
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
				<h3 class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Stacks</h3>
				<span class="text-xs text-fg-muted">
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
					<div class="flex h-full items-center justify-center text-sm text-fg-muted">
						No stacks configured. Add stacks in the scout step.
					</div>
				{:else if hasMultiItemGroups}
					<div class="flex flex-col gap-4">
						{#each stackGroups as group (group.label)}
							<div class="flex flex-col">
								<!-- Tab header -->
								<div
									class="flex h-ui-md w-fit items-center rounded-t-lg border-x border-t border-fg-muted/30 bg-panel px-3"
								>
									<span class="truncate text-xs font-medium text-fg-muted">{group.label}</span>
								</div>
								<!-- Stack rows -->
								<div class="flex flex-col overflow-hidden rounded-tr-lg rounded-b-lg border border-fg-muted/30">
									{#each group.stacks as stack (`${stack.profile_id}:${stack.row},${stack.col}`)}
										<div
											data-stack-status={status(stack)}
											class="relative flex h-ui-md items-center gap-3 overflow-hidden border-b border-fg-muted/30 px-3 text-xs last:border-b-0"
										>
											<span class="min-w-0 flex-1 truncate text-fg">
												{sanitizeString(stack.profile_id)}
												<span class="ml-4 text-fg-muted">R{stack.row}, C{stack.col}</span>
												<span class="ml-4 text-fg-muted/60">{stack.x_um.toFixed(0)} × {stack.y_um.toFixed(0)} µm</span>
											</span>
											<span class="shrink-0 font-mono text-fg-muted">
												{formatZ(stack.z_start_um)} → {formatZ(stack.z_end_um)} µm
											</span>
											<span class="shrink-0 text-fg-muted">{stack.num_frames} slices</span>
											{#if status(stack) === 'acquiring'}
												<DotsSpinner width="14" height="14" class="shrink-0 text-(--stack-status)" />
											{:else if status(stack) === 'completed'}
												<Check width="14" height="14" class="shrink-0 text-(--stack-status)" />
											{:else if status(stack) === 'failed'}
												<AlertCircleOutline width="14" height="14" class="shrink-0 text-(--stack-status)" />
											{:else if status(stack) === 'skipped'}
												<Minus width="14" height="14" class="shrink-0 text-(--stack-status)" />
											{:else}
												<LucideCircle width="12" height="12" class="shrink-0 text-(--stack-status)" />
											{/if}
											<Progress.Root
												value={fakeProgress(status(stack))}
												max={100}
												class="absolute inset-0 -z-10 bg-(--stack-status)/15"
												style="transform: scaleX({fakeProgress(status(stack)) / 100}); transform-origin: left"
											/>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="flex flex-col overflow-hidden rounded-lg border border-fg-muted/30">
						{#each session.plan.stacks as stack (`${stack.profile_id}:${stack.row},${stack.col}`)}
							<div
								data-stack-status={status(stack)}
								class="relative flex h-ui-md items-center gap-3 overflow-hidden border-b border-fg-muted/30 px-3 text-xs last:border-b-0"
							>
								<span class="min-w-0 flex-1 truncate text-fg">
									{sanitizeString(stack.profile_id)}
									<span class="ml-4 text-fg-muted">R{stack.row}, C{stack.col}</span>
									<span class="ml-4 text-fg-muted/60">{stack.x_um.toFixed(0)} × {stack.y_um.toFixed(0)} µm</span>
								</span>
								<span class="shrink-0 font-mono text-fg-muted">
									{formatZ(stack.z_start_um)} → {formatZ(stack.z_end_um)} µm
								</span>
								<span class="shrink-0 text-fg-muted">{stack.num_frames} slices</span>
								{#if status(stack) === 'acquiring'}
									<DotsSpinner width="14" height="14" class="shrink-0 text-(--stack-status)" />
								{:else if status(stack) === 'completed'}
									<Check width="14" height="14" class="shrink-0 text-(--stack-status)" />
								{:else if status(stack) === 'failed'}
									<AlertCircleOutline width="14" height="14" class="shrink-0 text-(--stack-status)" />
								{:else if status(stack) === 'skipped'}
									<Minus width="14" height="14" class="shrink-0 text-(--stack-status)" />
								{:else}
									<LucideCircle width="12" height="12" class="shrink-0 text-(--stack-status)" />
								{/if}
								<Progress.Root
									value={fakeProgress(status(stack))}
									max={100}
									class="absolute inset-0 -z-10 bg-(--stack-status)/15"
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
	:global(.profile-chip.svelte-dnd-dragging) {
		opacity: 0.4;
		transform: scale(0.95);
	}

	:global(.profile-chip.svelte-dnd-drop-target) {
		outline: none;
		box-shadow: 0 0 0 2px var(--color-info);
		transform: scale(1.05);
	}
</style>
