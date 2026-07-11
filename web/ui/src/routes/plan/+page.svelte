<script lang="ts">
  import { Popover } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { PersistedState, watch } from 'runed';
  import type { Component } from 'svelte';

  import { GridCanvas } from '$lib/grid';
  import { getTaskSelection } from '$lib/grid/selection.svelte';
  import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Crosshair, TrashCanOutline } from '$lib/icons';
  import { Button, Checkbox, Dialog, Select } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { getVoxelApp, type TaskPatch, type TileOrder } from '$lib/model';
  import { Input, SpinBox } from '$lib/prop/numeric';
  import { cn, sanitizeString, toastError } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const selection = getTaskSelection();

  // Stored in µm, like task positions; displayed/entered through the active unit.
  let nudgeStep = $state(100);

  // --- Space units: a display/entry lens over µm-stored values ---

  interface SpaceUnit {
    value: 'mm' | 'um';
    label: string;
    scale: number; // µm per unit
    step: number; // fine step (0.1 µm resolution)
    bigStep: number; // coarse step (10 µm)
    decimals: number; // display precision
  }

  const SPACE_UNITS: SpaceUnit[] = [
    { value: 'mm', label: 'mm', scale: 1000, step: 0.0001, bigStep: 0.01, decimals: 4 },
    { value: 'um', label: 'µm', scale: 1, step: 0.1, bigStep: 10, decimals: 1 }
  ];
  const SPACE_UNIT_OPTIONS = SPACE_UNITS.map((u) => ({ value: u.value, label: u.label }));

  const spaceUnit = new PersistedState<SpaceUnit['value']>('acquire.spaceUnit', 'mm');
  const unit = $derived(SPACE_UNITS.find((u) => u.value === spaceUnit.current) ?? SPACE_UNITS[0]);

  const TILE_ORDER_OPTIONS: { value: TileOrder; label: string }[] = [
    { value: 'sweep_row', label: 'Sweep Row' },
    { value: 'sweep_column', label: 'Sweep Column' },
    { value: 'snake_row', label: 'Snake Row' },
    { value: 'snake_column', label: 'Snake Column' },
    { value: 'nearest_neighbor', label: 'Nearest Neighbor' },
    { value: 'optimized', label: 'Optimized' },
    { value: 'custom', label: 'Custom' }
  ];

  // --- Rows: placed tasks in traversal (taskTiles) order ---

  interface TaskRow {
    taskId: string;
    x: number;
    y: number;
    start: number;
    end: number;
    profileIds: string[];
    order: number;
  }

  const rows = $derived.by<TaskRow[]>(() => {
    const inst = instrument;
    if (!inst) return [];
    return inst.taskTiles.map((tile, i) => {
      const t = inst.state.tasks[tile.task_id];
      return {
        taskId: tile.task_id,
        x: tile.x,
        y: tile.y,
        start: t?.start ?? 0,
        end: t?.end ?? 0,
        profileIds: t?.profile_ids ?? [],
        order: i + 1
      };
    });
  });

  const selectedRows = $derived(rows.filter((r) => selection.has(r.taskId)));
  const hasSelection = $derived(selectedRows.length > 0);
  const allSelected = $derived(rows.length > 0 && selectedRows.length === rows.length);
  const someSelected = $derived(hasSelection && !allSelected);

  function toggleAll(checked: boolean) {
    if (checked) selection.add(...rows.map((r) => r.taskId));
    else selection.clear();
  }

  function profileLabel(id: string): string {
    return instrument?.imaging.profiles[id]?.label || sanitizeString(id);
  }

  const allProfileIds = $derived(Object.keys(instrument?.imaging.profiles ?? {}));

  // Frames a profile captures over this task's Z-range: ⌊range / z_step⌋ + 1.
  function framesFor(row: TaskRow, profileId: string): number {
    const zStep = instrument?.imaging.profiles[profileId]?.z_step ?? 0;
    return zStep > 0 ? Math.floor(Math.abs(row.end - row.start) / zStep) + 1 : 0;
  }

  // Add/remove a profile across the selection (or just this row), keyed off the clicked row's membership.
  function toggleProfile(row: TaskRow, profileId: string) {
    const targets = selection.has(row.taskId) && selectedRows.length > 1 ? selectedRows : [row];
    const shouldAdd = !row.profileIds.includes(profileId);
    const patches = Object.fromEntries(
      targets.map((r) => {
        const next = shouldAdd
          ? r.profileIds.includes(profileId)
            ? r.profileIds
            : [...r.profileIds, profileId]
          : r.profileIds.filter((p) => p !== profileId);
        return [r.taskId, { profile_ids: next }];
      })
    );
    toastError(instrument?.updateTasks(patches));
  }

  // --- Actions (batched) ---

  function applyToSelected(patchFor: (r: TaskRow) => TaskPatch) {
    if (selectedRows.length === 0) return;
    toastError(instrument?.updateTasks(Object.fromEntries(selectedRows.map((r) => [r.taskId, patchFor(r)]))));
  }

  const applyNudge = (dx: number, dy: number) => applyToSelected((r) => ({ x: r.x + dx, y: r.y + dy }));

  // Applies a field patch to every selected task when this row is part of a multi-selection, else just this row.
  function applyField(row: TaskRow, field: 'x' | 'y' | 'start' | 'end', value: number) {
    const targets = selection.has(row.taskId) && selectedRows.length > 1 ? selectedRows : [row];
    toastError(instrument?.updateTasks(Object.fromEntries(targets.map((r) => [r.taskId, { [field]: value }]))));
  }

  const setField = (row: TaskRow, field: 'x' | 'y' | 'start' | 'end', value: number) =>
    applyField(row, field, value * unit.scale);

  // Current stage value for a field: X/Y are relative to the axis lower limit; Z start/end are absolute stage Z.
  function stageValue(field: 'x' | 'y' | 'start' | 'end'): number | undefined {
    const s = instrument?.stage;
    if (field === 'start' || field === 'end') return s?.z?.position?.value;
    const axis = field === 'x' ? s?.x : s?.y;
    return axis ? (axis.position?.value ?? 0) - (axis.lowerLimit?.value ?? 0) : undefined;
  }

  // Match-stage from the column headers: applies the current stage value to every selected task.
  function matchStageSelection(field: 'x' | 'y' | 'start' | 'end') {
    const value = stageValue(field);
    if (value == null || selectedRows.length === 0) return;
    toastError(instrument?.updateTasks(Object.fromEntries(selectedRows.map((r) => [r.taskId, { [field]: value }]))));
  }

  // A click/keydown that originated inside an editable cell — selection should ignore it (unless a modifier is held).
  const isEditTarget = (e: Event) => (e.target as HTMLElement | null)?.closest('[data-cell-edit]') != null;

  // --- Selection ---

  let lastClickedId = $state<string | null>(null);

  function handleRowClick(row: TaskRow, e: MouseEvent) {
    if (isEditTarget(e) && !(e.metaKey || e.ctrlKey || e.shiftKey)) {
      // Editing a cell in an unselected row makes that row the selection, so header actions target it;
      // editing a cell in an already-selected row leaves the selection intact (batch editing).
      if (!selection.has(row.taskId)) selection.select(row.taskId);
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      selection.toggle(row.taskId);
    } else if (e.shiftKey && lastClickedId) {
      const lastIdx = rows.findIndex((r) => r.taskId === lastClickedId);
      const curIdx = rows.findIndex((r) => r.taskId === row.taskId);
      if (lastIdx >= 0 && curIdx >= 0) {
        selection.clear();
        selection.add(...rows.slice(Math.min(lastIdx, curIdx), Math.max(lastIdx, curIdx) + 1).map((r) => r.taskId));
      } else {
        selection.select(row.taskId);
      }
    } else if (selection.has(row.taskId) && selection.size === 1) {
      selection.clear();
    } else {
      selection.select(row.taskId);
    }
    lastClickedId = row.taskId;
  }

  // Auto-scroll the table to the first selected task (e.g. selected from the canvas)
  watch(
    () => selection.list[0],
    (first) => {
      if (first) document.getElementById(`task-${first}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  );

  // --- Delete ---

  let deleteDialogOpen = $state(false);

  function deleteSelected() {
    toastError(instrument?.removeTasks(selection.list));
    deleteDialogOpen = false;
  }
</script>

{#snippet headerMatch(field: 'x' | 'y' | 'start' | 'end')}
  <button
    type="button"
    title="Match stage for selected tasks"
    disabled={!hasSelection}
    onclick={() => matchStageSelection(field)}
    class="flex size-4 shrink-0 items-center justify-center rounded text-fg-faint transition-colors hover:text-fg disabled:pointer-events-none"
  >
    <Crosshair width="12" height="12" />
  </button>
{/snippet}

{#snippet taskRow(row: TaskRow, selected: boolean)}
  <div
    id="task-{row.taskId}"
    role="row"
    tabindex="0"
    aria-selected={selected}
    class={cn(
      'col-span-full grid cursor-default grid-cols-subgrid text-left text-sm text-fg-muted transition-colors select-none',
      selected ? 'bg-element-selected/50' : 'hover:bg-element-hover'
    )}
    onclick={(e) => handleRowClick(row, e)}
    onkeydown={(e) => {
      if (isEditTarget(e)) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selection.select(row.taskId);
      }
    }}
  >
    <!-- Selection checkbox (always visible; checked when selected) -->
    <span class="cell cell-first justify-center">
      <button
        type="button"
        role="checkbox"
        aria-checked={selected}
        title={selected ? 'Deselect task' : 'Select task'}
        onclick={(e) => {
          e.stopPropagation();
          selection.toggle(row.taskId);
        }}
        onkeydown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
        }}
        class={cn(
          'flex size-3.5 cursor-pointer items-center justify-center rounded border transition-colors',
          selected ? 'border-primary bg-primary text-primary-fg' : 'border-input bg-element-bg hover:border-fg-muted'
        )}
      >
        {#if selected}<Check width="9" height="9" />{/if}
      </button>
    </span>
    <span class="cell justify-end text-fg-faint tabular-nums">#{row.order}</span>
    <span data-cell-edit class="cell justify-end focus-within:text-fg">
      <Input
        model={{
          value: row.x / unit.scale,
          onChange: (v) => setField(row, 'x', v),
          step: unit.step,
          bigStep: unit.bigStep
        }}
        decimals={unit.decimals}
        numCharacters={8}
        align="right"
        class="text-xs leading-none px-0.5"
      />
    </span>
    <span data-cell-edit class="cell justify-end focus-within:text-fg">
      <Input
        model={{
          value: row.y / unit.scale,
          onChange: (v) => setField(row, 'y', v),
          step: unit.step,
          bigStep: unit.bigStep
        }}
        decimals={unit.decimals}
        numCharacters={8}
        align="right"
        class="text-xs leading-none px-0.5"
      />
    </span>
    <span data-cell-edit class="cell justify-end focus-within:text-fg">
      <Input
        model={{
          value: row.start / unit.scale,
          onChange: (v) => setField(row, 'start', v),
          step: unit.step,
          bigStep: unit.bigStep
        }}
        decimals={unit.decimals}
        numCharacters={8}
        align="right"
        class="text-xs leading-none px-0.5"
      />
    </span>
    <span data-cell-edit class="cell justify-end focus-within:text-fg">
      <Input
        model={{
          value: row.end / unit.scale,
          onChange: (v) => setField(row, 'end', v),
          step: unit.step,
          bigStep: unit.bigStep
        }}
        decimals={unit.decimals}
        numCharacters={8}
        align="right"
        class="text-xs leading-none px-0.5"
      />
    </span>
    <div data-cell-edit class="cell justify-end">
      <Popover.Root>
        <Popover.Trigger
          class="flex max-w-full flex-wrap justify-end gap-1 rounded px-1 py-0.5 hover:bg-element-hover"
          title="Edit profiles"
        >
          {#if row.profileIds.length === 0}
            <span class="text-fg-faint">＋</span>
          {:else}
            {#each row.profileIds as id (id)}
              <span
                class={cn(
                  'truncate rounded-full px-1.5 py-px text-xs',
                  id === instrument?.activeProfileId ? 'bg-element-bg text-fg' : 'bg-element-bg/50 text-fg-muted'
                )}
              >
                {profileLabel(id)} <span class="text-fg-faint tabular-nums">{framesFor(row, id)}f</span>
              </span>
            {/each}
          {/if}
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content align="end" class="z-50 min-w-40 rounded border bg-floating p-1 text-fg shadow-md">
            {#each allProfileIds as id (id)}
              {@const active = row.profileIds.includes(id)}
              <button
                type="button"
                onclick={() => toggleProfile(row, id)}
                class="flex w-full items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-element-hover"
              >
                <span
                  class={cn(
                    'flex size-3.5 shrink-0 items-center justify-center rounded border',
                    active ? 'border-primary bg-primary text-primary-fg' : 'border-input bg-element-bg'
                  )}
                >
                  {#if active}<Check width="9" height="9" />{/if}
                </span>
                <span class="flex-1 text-left">{profileLabel(id)}</span>
                <span class="text-fg-faint tabular-nums">{framesFor(row, id)}f</span>
              </button>
            {/each}
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  </div>
{/snippet}

{#snippet nudgeButton(Icon: Component, label: string, onNudge: () => void)}
  <button
    class="flex size-ui-xs items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg disabled:pointer-events-none disabled:opacity-80"
    title={label}
    disabled={!hasSelection}
    onclick={onNudge}
  >
    <Icon width="18" height="18" />
  </button>
{/snippet}

<PaneGroup direction="vertical" autoSaveId="plan.grid" class="h-full">
  <Pane defaultSize={60} minSize={30}>
    <div class="flex h-full flex-col overflow-hidden">
        <div class="shrink-0 px-3 py-4">
            <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3">
                <span class="text-xs text-nowrap text-fg-muted tabular-nums">
                {selectedRows.length}/{rows.length} tasks
                </span>
                {#if instrument}
                <Select
                    size="xs"
                    class="w-full"
                    prefix="Traversal"
                    value={instrument.state.traversal}
                    options={TILE_ORDER_OPTIONS}
                    onchange={(v) => toastError(instrument.setTraversal(v as TileOrder))}
                />
                {/if}
            </div>
            <div class="flex items-center gap-3">
                <div class="flex items-center gap-1.5">
                <SpinBox
                    model={{
                    value: nudgeStep / unit.scale,
                    onChange: (v) => (nudgeStep = v * unit.scale),
                    min: unit.step,
                    step: unit.bigStep
                    }}
                    decimals={unit.decimals}
                    numCharacters={7}
                    size="xs"
                    steppers={false}
                    prefix="Nudge"
                    suffix={unit.label}
                />
                <div class="flex items-center gap-0.5">
                    {@render nudgeButton(ChevronLeft, 'Nudge −X', () => applyNudge(-nudgeStep, 0))}
                    {@render nudgeButton(ChevronRight, 'Nudge +X', () => applyNudge(nudgeStep, 0))}
                    {@render nudgeButton(ChevronUp, 'Nudge +Y', () => applyNudge(0, nudgeStep))}
                    {@render nudgeButton(ChevronDown, 'Nudge −Y', () => applyNudge(0, -nudgeStep))}
                </div>
                </div>
                <Select
                size="xs"
                class="w-24"
                prefix="Units"
                value={spaceUnit.current}
                options={SPACE_UNIT_OPTIONS}
                onchange={(v) => (spaceUnit.current = v as SpaceUnit['value'])}
                />
                <Button
                variant="secondary"
                size="xs"
                title="Delete selected tasks"
                disabled={!hasSelection}
                onclick={() => (deleteDialogOpen = true)}
                >
                <TrashCanOutline width="14" height="14" />
                Delete
                </Button>
            </div>
            </div>
        </div>
  <!-- Rows -->
  <div
    role="grid"
    aria-label="Task list"
    class="grid flex-1 auto-rows-min grid-cols-[auto_auto_auto_auto_auto_auto_1fr] content-start overflow-y-auto px-2"
  >
    {#if rows.length === 0}
      <div class="col-span-full flex min-h-32 items-center justify-center p-4">
        <p class="text-sm text-fg-faint">No tasks — add tasks from the grid</p>
      </div>
    {:else}
      <!-- Column header -->
      <div class="col-span-full grid grid-cols-subgrid text-sm font-medium text-fg-muted">
        <span class="cell cell-first cell-head justify-center">
          <Checkbox
            size="xs"
            checked={allSelected}
            indeterminate={someSelected}
            disabled={rows.length === 0}
            onchange={toggleAll}
          />
        </span>
        <span class="cell cell-head justify-end">#</span>
        <span class="cell cell-head justify-between">{@render headerMatch('x')}X</span>
        <span class="cell cell-head justify-between">{@render headerMatch('y')}Y</span>
        <span class="cell cell-head justify-between">{@render headerMatch('start')}Z Start</span>
        <span class="cell cell-head justify-between">{@render headerMatch('end')}Z End</span>
        <span class="cell cell-head justify-end"><span class="pr-2">Profiles</span></span>
      </div>
      {#each rows as row (row.taskId)}
        {@render taskRow(row, selection.has(row.taskId))}
      {/each}
    {/if}
    </div>
    </div>
  </Pane>
  <PaneDivider direction="horizontal" />
  <Pane defaultSize={40} minSize={20} class="min-w-0 overflow-hidden">
    {#if instrument}
      <GridCanvas {instrument} />
    {/if}
  </Pane>
</PaneGroup>

<Dialog.Root bind:open={deleteDialogOpen}>
  <Dialog.Portal>
    <Dialog.Overlay />
    <Dialog.Content>
      <Dialog.Header>
        <Dialog.Title>Delete task{selectedRows.length !== 1 ? 's' : ''}</Dialog.Title>
        <Dialog.Description>
          Delete {selectedRows.length} selected task{selectedRows.length !== 1 ? 's' : ''}? This can't be undone.
        </Dialog.Description>
      </Dialog.Header>
      <Dialog.Footer>
        <button
          onclick={() => (deleteDialogOpen = false)}
          class="rounded border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
        >
          Cancel
        </button>
        <button
          onclick={deleteSelected}
          class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
        >
          Delete
        </button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<style>
  /* Task-table cell chrome: single-pixel grid lines (right + bottom; first column adds left, header adds top). */
  .cell {
    --cell-border: 1px solid var(--color-border-faint);
    display: flex;
    align-items: center;
    padding: 0.25rem 0.5rem;
    border-right: var(--cell-border);
    border-bottom: var(--cell-border);
    transition: background-color 150ms;
  }
  .cell-first {
    border-left: var(--cell-border);
  }
  .cell-head {
    border-top: var(--cell-border);
  }
</style>
