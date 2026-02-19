<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Select, SpinBox } from '$lib/ui/primitives';
	import type { Session } from '$lib/main';
	import { getStackStatusColor, type TileOrder } from '$lib/main/types';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const TILE_ORDER_OPTIONS: { value: TileOrder; label: string }[] = [
		{ value: 'row_wise', label: 'Row-wise' },
		{ value: 'column_wise', label: 'Column-wise' },
		{ value: 'snake_row', label: 'Snake (Row)' },
		{ value: 'snake_column', label: 'Snake (Column)' }
	];

	function handleTileOrderChange(value: string) {
		session.setTileOrder(value as TileOrder);
	}

	let selectedTile = $derived(session.selectedTiles[0] ?? null);
	let stack = $derived(
		selectedTile ? (session.stacks.find((s) => s.row === selectedTile.row && s.col === selectedTile.col) ?? null) : null
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
		return { start: session.gridConfig.default_z_start_um, end: session.gridConfig.default_z_end_um };
	}

	$effect(() => {
		void selectedTile;
		isEditing = false;
		const defaults = getDefaultZ();
		zStartInput = defaults.start;
		zEndInput = defaults.end;
	});

	let isDirty = $derived(stack ? zStartInput !== stack.z_start_um || zEndInput !== stack.z_end_um : true);
	let numSlices = $derived(Math.ceil(Math.abs(zEndInput - zStartInput) / session.gridConfig.z_step_um));
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
	<div
		class="flex h-6 cursor-default items-stretch rounded border border-muted bg-transparent font-mono text-[0.65rem]"
	>
		<span class="flex shrink-0 items-center ps-1.5 pe-2 text-muted-foreground">{label}</span>
		<span class="flex flex-1 items-center px-0.5 text-foreground">{value}</span>
		<span class="flex items-center pe-1.5 text-muted-foreground">{unit}</span>
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
			size="sm"
			prefix={label}
			suffix="µm"
			{onChange}
		/>
	{:else}
		{@render staticItem(label, String(displayValue ?? '—'), 'µm')}
	{/if}
{/snippet}

{#if session.zAxis && selectedTile}
	<div class="flex flex-col border-y border-border bg-accent/30">
		<div class="flex flex-col gap-2 p-4 pt-3">
			<div class="flex items-center justify-between">
				<span class="flex items-center gap-3">
					<span class="font-mono text-xs font-semibold {getStackStatusColor(stack?.status ?? null)}">
						R{selectedTile.row}, C{selectedTile.col}
					</span>
					{#if stack}<span class="text-[0.6rem] {getStackStatusColor(stack.status)}">{stack.status}</span>{/if}
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

			<div class="grid grid-cols-2 gap-x-8 gap-y-2 text-[0.65rem]">
				{@render staticItem('X', formatMm(selectedTile.x_um), 'mm')}
				{@render staticItem('Y', formatMm(selectedTile.y_um), 'mm')}
				{@render staticItem('W', formatMm(selectedTile.w_um, 1), 'mm')}
				{@render staticItem('H', formatMm(selectedTile.h_um, 1), 'mm')}

				{@render editableZItem(
					'Z0',
					zStartInput,
					stack?.z_start_um ?? null,
					updateZStart,
					() => Math.round(session.zAxis!.position * 1000),
					session.zAxis.lowerLimit * 1000,
					session.zAxis.upperLimit * 1000
				)}
				{@render editableZItem(
					'Z1',
					zEndInput,
					stack?.z_end_um ?? null,
					updateZEnd,
					() => Math.round(session.zAxis!.position * 1000),
					session.zAxis.lowerLimit * 1000,
					session.zAxis.upperLimit * 1000
				)}

				{@render staticItem('Slices', isEditing ? String(numSlices) : (stack?.num_frames?.toString() ?? '—'))}
				{@render staticItem('Profile', stack?.profile_id ?? '—')}
			</div>
		</div>
	</div>
{/if}

<div class="flex items-center justify-between border-t border-border p-3 text-[0.65rem]">
	<span class="text-muted-foreground">Order</span>
	<Select value={session.tileOrder} options={TILE_ORDER_OPTIONS} onchange={handleTileOrderChange} size="sm" />
	{@render staticItem('Z Step', String(session.gridConfig.z_step_um), 'µm')}
</div>
