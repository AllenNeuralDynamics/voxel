<script lang="ts">
  import { watch } from 'runed';
  import { type Component, onDestroy } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getTaskSelection } from '$lib/grid/selection.svelte';
  import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Close, Plus, TrashCanOutline } from '$lib/icons';
  import { Button, buttonVariants, Dialog, DropdownMenu, Select } from '$lib/kit';
  import { getVoxelStation, type Instrument, type TaskPatch, type TileOrder } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { cn, displayName, toastError } from '$lib/utils';

  import StageNumericField from './StageNumericField.svelte';

  const app = getVoxelStation();
  const instrument = $derived(app.instrument?.id === page.params.instrumentId ? app.instrument : null);
  const selection = getTaskSelection();
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const preferenceKey = $derived(`${page.params.stationId ?? ''}/${page.params.instrumentId ?? ''}`);
  const coordinateFormat = new Intl.NumberFormat(undefined, {
    minimumSignificantDigits: 4,
    maximumSignificantDigits: 4,
    useGrouping: false
  });
  const formatCoordinate = (value: number) =>
    Number.isFinite(value) ? coordinateFormat.format(value / unit.scale) : '—';
  const disabled = $derived(!instrument || instrument.mode === 'capture');
  let editorTab = $state<'geometry' | 'profiles' | null>(null);
  const editorSections = [
    { id: 'geometry', label: 'Geometry' },
    { id: 'profiles', label: 'Profiles' }
  ] as const;
  let nudgeStep = $state(100);

  const TILE_ORDER_OPTIONS: { value: TileOrder; label: string }[] = [
    { value: 'sweep_row', label: 'Sweep Row' },
    { value: 'sweep_column', label: 'Sweep Column' },
    { value: 'snake_row', label: 'Snake Row' },
    { value: 'snake_column', label: 'Snake Column' },
    { value: 'nearest_neighbor', label: 'Nearest Neighbor' },
    { value: 'optimized', label: 'Optimized' },
    { value: 'custom', label: 'Custom' }
  ];

  type Field = 'x' | 'y' | 'start' | 'end';
  const fields: { key: Field; label: string }[] = [
    { key: 'x', label: 'X position' },
    { key: 'y', label: 'Y position' },
    { key: 'start', label: 'Z start' },
    { key: 'end', label: 'Z end' }
  ];
  const rows = $derived(
    instrument?.taskTiles.map((tile, i) => ({
      ...instrument!.state.tasks[tile.task_id],
      taskId: tile.task_id,
      x: tile.x,
      y: tile.y,
      order: i + 1
    })) ?? []
  );
  const selectedRows = $derived(rows.filter((row) => selection.has(row.taskId)));
  const hasSelection = $derived(selectedRows.length > 0);
  const allProfileIds = $derived(Object.keys(instrument?.imaging.profiles ?? {}));
  const currentPosition = $derived.by(() => {
    const x = instrument?.stage.x.position?.value;
    const y = instrument?.stage.y.position?.value;
    return x != null && y != null && Number.isFinite(x) && Number.isFinite(y) ? ([x, y] as [number, number]) : null;
  });
  const currentTaskRange = $derived.by(() => {
    const saved = prefs.plan.taskDefaults.get()[preferenceKey];
    if (saved) return { start: saved.start, end: saved.end };
    const z = instrument?.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });

  async function addAtCurrentPosition() {
    const inst = instrument;
    if (!inst || !currentPosition || !currentTaskRange || inst.mode === 'capture' || inst.edits.busy) return;
    const change = await inst.addTasks([currentPosition], currentTaskRange);
    const defaults = prefs.plan.taskDefaults.get();
    if (!defaults[preferenceKey]) {
      prefs.plan.taskDefaults.set({
        ...defaults,
        [preferenceKey]: { ...currentTaskRange, overlap: 0.1 }
      });
    }
    const id = Object.keys(change.after)[0];
    if (instrument === inst && id) selection.select(id);
  }

  function profileLabel(id: string): string {
    return instrument?.imaging.profiles[id]?.label || displayName(id);
  }

  function framesFor(row: (typeof rows)[number], profileId: string): number {
    const step = instrument?.imaging.profiles[profileId]?.z_step ?? 0;
    return step > 0 ? Math.floor(Math.abs(row.end - row.start) / step) + 1 : 0;
  }

  function commonValue(field: Field): number | undefined {
    const first = selectedRows[0]?.[field];
    return selectedRows.every((row) => row[field] === first) ? first : undefined;
  }

  function applyToSelected(patchFor: (row: (typeof rows)[number]) => TaskPatch) {
    if (disabled || !hasSelection) return;
    toastError(instrument?.updateTasks(Object.fromEntries(selectedRows.map((row) => [row.taskId, patchFor(row)]))));
  }

  function setProfile(profileId: string, checked: boolean) {
    applyToSelected((row) => ({
      profile_ids: checked
        ? [...new Set([...row.profile_ids, profileId])]
        : row.profile_ids.filter((id) => id !== profileId)
    }));
  }

  // A field keeps its original targets until commit, including selection changes from the canvas.
  let fieldEdit:
    | {
        field: Field;
        ids: string[];
        instrument: Instrument;
        finish: () => void;
      }
    | undefined;

  function startField(field: Field): (() => void) | undefined {
    cancelField();
    if (!instrument || disabled) return;
    const release = instrument.edits.hold();
    let released = false;
    const edit = {
      field,
      ids: selectedRows.map((row) => row.taskId),
      instrument,
      finish: () => {
        if (released) return;
        released = true;
        if (fieldEdit === edit) fieldEdit = undefined;
        release();
      }
    };
    fieldEdit = edit;
    return edit.finish;
  }

  function commitField(field: Field, value: number | null) {
    const edit = fieldEdit;
    if (!edit || edit.field !== field || value == null || instrument !== edit.instrument || disabled) return;
    toastError(edit.instrument.updateTasks(Object.fromEntries(edit.ids.map((id) => [id, { [field]: value }]))));
  }

  function cancelField() {
    const edit = fieldEdit;
    fieldEdit = undefined;
    edit?.finish();
  }

  onDestroy(cancelField);

  let lastClickedId: string | null = null;
  function selectTask(id: string, event: MouseEvent) {
    if (event.metaKey || event.ctrlKey) selection.toggle(id);
    else if (event.shiftKey && lastClickedId) {
      const first = rows.findIndex((row) => row.taskId === lastClickedId);
      const last = rows.findIndex((row) => row.taskId === id);
      if (first < 0) selection.select(id);
      else {
        selection.clear();
        selection.add(...rows.slice(Math.min(first, last), Math.max(first, last) + 1).map((row) => row.taskId));
      }
    } else if (selection.has(id) && selection.size === 1) selection.clear();
    else selection.select(id);
    lastClickedId = id;
  }

  watch(
    () => selection.list[0],
    (first) => {
      if (first) document.getElementById(`task-${first}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  );

  let deleteDialogOpen = $state(false);
  let deletingIds = $state<string[]>([]);
  function deleteSelected() {
    if (!disabled) toastError(instrument?.removeTasks(deletingIds));
    deleteDialogOpen = false;
  }
</script>

{#snippet nudgeButton(Icon: Component, label: string, dx: number, dy: number)}
  <Button
    variant="outline"
    size="xs"
    title={label}
    aria-label={label}
    disabled={disabled || !hasSelection}
    onclick={() => applyToSelected((row) => ({ x: row.x + dx, y: row.y + dy }))}
  >
    <Icon width="16" height="16" />
  </Button>
{/snippet}

{#snippet selectionToolbar()}
  <div
    class="flex min-h-pane-footer shrink-0 flex-wrap items-center justify-between gap-2 border-t border-line-muted px-4 py-2"
  >
    <div class="flex items-center gap-1 text-base text-fg-muted">
      <span class="tabular-nums">
        {#if hasSelection}{selectedRows.length} of {rows.length} tasks{:else}{rows.length} tasks{/if}
      </span>
      {#if hasSelection}
        <Button
          variant="ghost"
          size="xs"
          title="Clear selection"
          aria-label="Clear selection"
          onclick={() => selection.clear()}
        >
          <Close class="size-3.5" />
        </Button>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      <Button
        variant="outline"
        size="icon-xs"
        title="Delete selected tasks"
        aria-label="Delete selected tasks"
        disabled={disabled || !hasSelection}
        onclick={() => {
          deletingIds = selectedRows.map((row) => row.taskId);
          deleteDialogOpen = true;
        }}
      >
        <TrashCanOutline class="size-3.5" />
      </Button>
      <div
        role="group"
        aria-label="Task editing sections"
        class="inline-flex divide-x divide-line-faint overflow-hidden rounded border border-control-line"
      >
        {#each editorSections as { id, label } (id)}
          <button
            id="task-editor-toggle-{id}"
            type="button"
            aria-pressed={editorTab === id}
            aria-expanded={editorTab === id}
            aria-controls="plan-task-editor"
            class={cn(
              'h-ui-xs px-2 text-base transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-border-focused',
              editorTab === id ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover'
            )}
            onclick={() => (editorTab = editorTab === id ? null : id)}>{label}</button
          >
        {/each}
      </div>
    </div>
  </div>
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Plan' }]}>
    {#snippet trailing()}
      {#if instrument}
        <Select
          size="sm"
          class="w-46"
          prefix="Order"
          value={instrument.state.traversal}
          options={TILE_ORDER_OPTIONS}
          onchange={(v) => toastError(instrument.setTraversal(v as TileOrder))}
        />
      {/if}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          class={buttonVariants({ variant: 'secondary', size: 'sm', class: 'text-base font-normal' })}
          disabled={!instrument || instrument.mode === 'capture' || instrument.edits.busy}
        >
          <Plus class="size-4" />
          Add Tasks
          <ChevronDown class="size-3.5" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" class="font-normal">
          <DropdownMenu.Item
            class="text-base"
            disabled={!currentPosition}
            title="Uses the active profile and the Grid's default Z range"
            onclick={() => toastError(addAtCurrentPosition())}
          >
            At current position
          </DropdownMenu.Item>
          <DropdownMenu.Item
            class="text-base"
            onclick={() =>
              goto(
                resolve('/stations/[stationId]/instruments/[instrumentId]/plan/add', {
                  stationId: page.params.stationId ?? '',
                  instrumentId: page.params.instrumentId ?? ''
                })
              )}
          >
            Define region…
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    {/snippet}
  </PageHeader>

  <div class="flex min-h-0 flex-1 flex-col">
    <div class="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
      {#if rows.length === 0}
        <p class="py-10 text-center text-lg text-fg-faint">No tasks — use Add Tasks to get started</p>
      {:else}
        <ul aria-label="Tasks" class="space-y-3">
          {#each rows as row (row.taskId)}
            <li>
              <button
                id="task-{row.taskId}"
                type="button"
                aria-pressed={selection.has(row.taskId)}
                class={cn(
                  'w-full min-w-0 rounded-lg border px-3 py-2 text-left text-base transition-colors focus-visible:ring-2 focus-visible:ring-border-focused focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none',
                  selection.has(row.taskId)
                    ? 'border-line-selected bg-element-selected'
                    : 'border-line-muted hover:border-line-muted hover:bg-element-hover/50'
                )}
                onclick={(event) => selectTask(row.taskId, event)}
              >
                <span class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span class="text-lg">Task {row.order}</span>
                  <span class="ml-auto flex max-w-full flex-wrap items-center justify-end gap-1 text-sm tabular-nums">
                    <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap">
                      <span class="mr-1 text-fg-muted">X</span>{formatCoordinate(row.x)}
                    </span>
                    <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap">
                      <span class="mr-1 text-fg-muted">Y</span>{formatCoordinate(row.y)}
                    </span>
                    <span class="inline-flex items-center gap-1 whitespace-nowrap">
                      <span class="rounded-sm bg-element-bg px-1.5 py-0.5">
                        <span class="mr-1 text-fg-muted">Z</span>{formatCoordinate(row.start)} – {formatCoordinate(
                          row.end
                        )}
                      </span>
                      <span class="text-fg-muted">{unit.label}</span>
                    </span>
                  </span>
                </span>
                <span class="my-1 grid gap-1">
                  {#each row.profile_ids as id (id)}
                    <span class="flex items-baseline justify-between gap-3">
                      <span class="truncate text-fg-muted">{profileLabel(id)}</span>
                      <span class="shrink-0 text-fg-faint tabular-nums">{framesFor(row, id)} frames</span>
                    </span>
                  {:else}
                    <span class="text-fg-faint">No profiles assigned</span>
                  {/each}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
    <footer class={cn('flex shrink-0 flex-col', editorTab && 'h-[min(18rem,55%)]')}>
      {@render selectionToolbar()}
      {#if editorTab}
        <div
          id="plan-task-editor"
          role="region"
          aria-labelledby="task-editor-toggle-{editorTab}"
          class="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 pb-4"
        >
          {#if hasSelection}
            {#if editorTab === 'geometry'}
              <fieldset {disabled} class="grid grid-cols-2 gap-x-3 gap-y-5 disabled:opacity-50">
                {#each fields as { key, label } (key)}
                  {@const value = commonValue(key)}
                  <div class="min-w-0 space-y-1 text-base">
                    <label for="task-edit-{key}" class="text-fg-muted">{label}</label>
                    <StageNumericField
                      id="task-edit-{key}"
                      stage={instrument?.stage}
                      axis={key === 'start' || key === 'end' ? 'z' : key}
                      value={value ?? null}
                      step={unit.step * unit.scale}
                      displayScale={unit.scale}
                      decimals={unit.decimals}
                      placeholder="Mixed"
                      suffix={unit.label}
                      size="sm"
                      class="w-full"
                      oneditstart={() => startField(key)}
                      oncommit={(next) => commitField(key, next)}
                      {disabled}
                    />
                  </div>
                {/each}
              </fieldset>
              <div class="grid grid-cols-2 items-center gap-3">
                <SpinBox
                  class="w-full min-w-0"
                  model={{
                    value: nudgeStep,
                    onChange: (value) => (nudgeStep = value),
                    min: unit.step * unit.scale,
                    step: unit.bigStep * unit.scale
                  }}
                  displayScale={unit.scale}
                  decimals={unit.decimals}
                  numCharacters={6}
                  size="xs"
                  steppers={false}
                  prefix="Nudge"
                  suffix={unit.label}
                  {disabled}
                />
                <div class="grid min-w-0 grid-cols-4 gap-1">
                  {@render nudgeButton(ChevronLeft, 'Nudge −X', -nudgeStep, 0)}
                  {@render nudgeButton(ChevronRight, 'Nudge +X', nudgeStep, 0)}
                  {@render nudgeButton(ChevronUp, 'Nudge +Y', 0, nudgeStep)}
                  {@render nudgeButton(ChevronDown, 'Nudge −Y', 0, -nudgeStep)}
                </div>
              </div>
            {:else}
              <fieldset {disabled} class="space-y-2 text-base disabled:opacity-50">
                <legend class="mb-2 text-fg-muted">Profiles</legend>
                {#each allProfileIds as id (id)}
                  {@const count = selectedRows.filter((row) => row.profile_ids.includes(id)).length}
                  <label class="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={count === selectedRows.length}
                      indeterminate={count > 0 && count < selectedRows.length}
                      onchange={(event) => setProfile(id, event.currentTarget.checked)}
                    />
                    <span class="min-w-0 flex-1 truncate">{profileLabel(id)}</span>
                    {#if count > 0 && count < selectedRows.length}<span class="text-fg-faint">Some</span>{/if}
                  </label>
                {/each}
              </fieldset>
            {/if}
          {:else}
            <p class="text-base text-fg-muted">Select tasks in the list or on Stage to edit.</p>
          {/if}
        </div>
      {/if}
    </footer>
  </div>
</div>

<Dialog.Root bind:open={deleteDialogOpen}>
  <Dialog.Portal>
    <Dialog.Overlay />
    <Dialog.Content>
      <Dialog.Header>
        <Dialog.Title>Delete {deletingIds.length === 1 ? 'task' : 'tasks'}</Dialog.Title>
        <Dialog.Description
          >Delete {deletingIds.length} selected {deletingIds.length === 1 ? 'task' : 'tasks'}? You can undo this change.</Dialog.Description
        >
      </Dialog.Header>
      <Dialog.Footer>
        <Button variant="outline" onclick={() => (deleteDialogOpen = false)}>Cancel</Button>
        <Button variant="outline" {disabled} onclick={deleteSelected}>Delete</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
