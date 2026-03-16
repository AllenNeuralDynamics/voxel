<script lang="ts">
	import { TrashCanOutline, Check, Close, PencilOutline } from '$lib/icons';
	import { Select, SpinBox } from '$lib/ui/kit';
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type Interleaving, type TileOrder } from '$lib/main/types';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

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

	function handleTileOrderChange(value: string) {
		session.setTileOrder(value as TileOrder);
	}

	function handleInterleavingChange(value: string) {
		session.setInterleaving(value as Interleaving);
	}

	let profileStacks = $derived(session.stacks.filter((s) => s.profile_id === session.activeProfileId));

	let selectedTile = $derived(session.selectedTiles[0] ?? null);
	let stack = $derived(
		selectedTile ? (profileStacks.find((s) => s.row === selectedTile.row && s.col === selectedTile.col) ?? null) : null
	);

	let isEditing = $state(false);
	let zStartInput = $state(0);
	let zEndInput = $state(100);

	let lastZStart = $state<number | null>(null);
	let lastZEnd = $state<number | null>(null);

	function getDefaultZ(): { start: number; end: number } {
		if (stack) {
			return { start: stack.z_start_um, end: stack.z_end_um };
		}
		if (lastZStart !== null && lastZEnd !== null) {
			return { start: lastZStart, end: lastZEnd };
		}
		return { start: session.gridConfig?.default_z_start_um ?? 0, end: session.gridConfig?.default_z_end_um ?? 100 };
	}

	$effect(() => {
		void selectedTile;
		isEditing = false;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	});

	let isDirty = $derived(stack ? zStartInput !== stack.z_start_um || zEndInput !== stack.z_end_um : true);
	let numSlices = $derived(Math.ceil(Math.abs(zEndInput - zStartInput) / (session.gridConfig?.z_step_um ?? 1)));
	let hasStack = $derived(stack !== null);

	function formatMm(um: number, decimals: number = 2): string {
		return (um / 1000).toFixed(decimals);
	}

	function handleEdit() {
		isEditing = true;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	}

	function handleSubmit() {
		if (!selectedTile) return;
		const { row, col } = selectedTile;
		if (hasStack) {
			session.editStacks([{ row, col, zStartUm: zStartInput, zEndUm: zEndInput }]);
		} else {
			session.addStacks([{ row, col, zStartUm: zStartInput, zEndUm: zEndInput }]);
		}
		lastZStart = zStartInput;
		lastZEnd = zEndInput;
		isEditing = false;
	}

	function handleDelete() {
		if (!selectedTile) return;
		if (confirm('Delete this stack?')) {
			session.removeStacks([{ row: selectedTile.row, col: selectedTile.col }]);
		}
	}

	function handleCancel() {
		isEditing = false;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	}

	function updateZStart(value: number) {
		zStartInput = value;
	}

	function updateZEnd(value: number) {
		zEndInput = value;
	}
</script>

{#snippet staticItem(label: string, value: string, unit: string = '')}
	<div class="flex h-6 cursor-default items-stretch rounded border border-muted bg-transparent font-mono text-xs">
		<span class="text-fg-muted flex shrink-0 items-center ps-1.5 pe-2">{label}</span>
		<span class="text-fg flex flex-1 items-center px-0.5">{value}</span>
		<span class="text-fg-muted flex items-center pe-1.5">{unit}</span>
	</div>
{/snippet}

{#snippet editableZItem(
	label: string,
	inputValue: number,
	displayValue: number | null,
	onChange: (v: number) => void,
	getDefault: () => number,
	min: number,
	max: number
)}
	{#if isEditing}
		<SpinBox
			value={inputValue}
			{min}
			{max}
			snapValue={getDefault}
			step={0.1}
			decimals={1}
			numCharacters={5}
			size="xs"
			prefix={label}
			suffix="µm"
			{onChange}
		/>
	{:else}
		{@render staticItem(label, String(displayValue ?? '—'), 'µm')}
	{/if}
{/snippet}

{#if session.stage.z && selectedTile}
	<div class="bg-element-hover/30 flex flex-col border-y border-border">
		<div class="flex flex-col gap-2 p-4 pt-3">
			<div class="flex items-center justify-between">
				<span class="flex items-center gap-3">
					<span class="font-mono text-sm font-semibold {getStackStatusColor(stack?.status ?? null)}">
						R{selectedTile.row}, C{selectedTile.col}
					</span>
					{#if stack}<span class="text-xs {getStackStatusColor(stack.status)}">{stack.status}</span>{/if}
				</span>
				<div class="flex items-center gap-0.5">
					{#if isEditing}
						{#if hasStack}
							<button
								onclick={handleDelete}
								class="text-fg-muted hover:bg-element-hover rounded p-1 transition-colors hover:text-danger"
								title="Delete stack"
							>
								<TrashCanOutline width="14" height="14" />
							</button>
						{/if}
						{#if isDirty}
							<button
								onclick={handleSubmit}
								class="hover:bg-element-hover rounded p-1 text-success transition-colors hover:text-success"
								title={hasStack ? 'Save changes' : 'Add stack'}
							>
								<Check width="14" height="14" />
							</button>
						{/if}
						<button
							onclick={handleCancel}
							class="text-fg-muted hover:bg-element-hover hover:text-fg rounded p-1 transition-colors"
							title="Cancel"
						>
							<Close width="14" height="14" />
						</button>
					{:else}
						<button
							onclick={handleEdit}
							class="text-fg-muted hover:bg-element-hover hover:text-fg rounded p-1 transition-colors"
							title={hasStack ? 'Edit stack' : 'Add stack'}
						>
							<PencilOutline width="14" height="14" />
						</button>
					{/if}
				</div>
			</div>

			<div class="grid grid-cols-2 gap-x-8 gap-y-2 text-xs">
				{@render staticItem('X', formatMm(selectedTile.x_um), 'mm')}
				{@render staticItem('Y', formatMm(selectedTile.y_um), 'mm')}
				{@render staticItem('W', formatMm(selectedTile.w_um, 1), 'mm')}
				{@render staticItem('H', formatMm(selectedTile.h_um, 1), 'mm')}

				{@render editableZItem(
					'Z0',
					zStartInput,
					stack?.z_start_um ?? null,
					updateZStart,
					() => Math.round(session.stage.z!.position * 1000),
					session.stage.z.lowerLimit * 1000,
					session.stage.z.upperLimit * 1000
				)}
				{@render editableZItem(
					'Z1',
					zEndInput,
					stack?.z_end_um ?? null,
					updateZEnd,
					() => Math.round(session.stage.z!.position * 1000),
					session.stage.z.lowerLimit * 1000,
					session.stage.z.upperLimit * 1000
				)}

				{@render staticItem('Slices', isEditing ? String(numSlices) : (stack?.num_frames?.toString() ?? '—'))}
				{@render staticItem('Profile', stack?.profile_id ?? '—')}
			</div>
		</div>
	</div>
{/if}

<div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border p-3 text-xs">
	<span class="text-fg-muted">Order</span>
	<Select value={session.tileOrder} options={TILE_ORDER_OPTIONS} onchange={handleTileOrderChange} size="xs" />
	<span class="text-fg-muted">Interleaving</span>
	<Select value={session.interleaving} options={INTERLEAVING_OPTIONS} onchange={handleInterleavingChange} size="xs" />
	{@render staticItem('Z Step', String(session.gridConfig?.z_step_um ?? '—'), 'µm')}
</div>
