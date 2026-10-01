<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Close, GripVertical, Plus, TrashCanOutline } from '$lib/icons';
  import { Button, buttonVariants, Dialog, DropdownMenu, Select } from '$lib/kit';
  import * as Sortable from '$lib/kit/sortable';
  import {
    type EditContext,
    getVoxelStation,
    type Point2D,
    type TaskPatch,
    type TileOrder,
    type VolumeOrder
  } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { NumericField } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { displayName, toastError } from '$lib/utils';

  import StageNumericField from '../StageNumericField.svelte';
  import XYPointList from '../XYPointList.svelte';

  const app = getVoxelStation();
  const routeParams = $derived({
    stationId: page.params.stationId ?? '',
    instrumentId: page.params.instrumentId ?? ''
  });
  const instrument = $derived(app.instrument?.id === routeParams.instrumentId ? app.instrument : null);
  const taskId = $derived(page.params.taskId ?? '');
  const taskIndex = $derived(instrument?.plan.findIndex((candidate) => candidate.id === taskId) ?? -1);
  const task = $derived(taskIndex < 0 ? undefined : instrument?.plan[taskIndex]);
  const pointCount = $derived(task?.layout.points.length ?? 0);
  const areaPositionCount = $derived.by(() => {
    if (!instrument || !task || task.layout.type !== 'area') return undefined;
    const positions = new Set(
      instrument.plannedVolumes.filter((volume) => volume.task === task.id).map((volume) => `${volume.x}\0${volume.y}`)
    );
    return positions.size || undefined;
  });
  const minimumPoints = $derived(task?.layout.type === 'area' ? 3 : 1);
  const currentPosition = $derived.by(() => {
    const x = instrument?.stage.x.position?.value;
    const y = instrument?.stage.y.position?.value;
    return x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y) ? null : { x, y };
  });
  const canAddPoint = $derived(
    !!currentPosition &&
      !task?.layout.points.some((point) => point.x === currentPosition.x && point.y === currentPosition.y)
  );
  const availableProfiles = $derived(
    Object.keys(instrument?.imaging.profiles ?? {}).filter((profileId) => !task?.profiles.includes(profileId))
  );
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const planHref = $derived(resolve('/stations/[stationId]/instruments/[instrumentId]/plan', routeParams));
  const disabled = $derived(!instrument || instrument.mode === 'capture');

  const traversalOptions: { value: TileOrder; label: string }[] = [
    { value: 'sweep_row', label: 'Sweep rows' },
    { value: 'sweep_column', label: 'Sweep columns' },
    { value: 'snake_row', label: 'Snake rows' },
    { value: 'snake_column', label: 'Snake columns' },
    { value: 'nearest_neighbor', label: 'Nearest neighbor' },
    { value: 'optimized', label: 'Optimized' },
    { value: 'custom', label: 'As defined' }
  ];
  const volumeOrderOptions: { value: VolumeOrder; label: string }[] = [
    { value: 'position_major', label: 'Position first' },
    { value: 'profile_major', label: 'Profile first' }
  ];

  let deleteDialogOpen = $state(false);

  function patchTask(patch: TaskPatch, context: EditContext = {}): void {
    if (!instrument || !task || disabled) return;
    toastError(instrument.updateTask(task.id, patch, context));
  }

  function replacePoints(points: Point2D[]): void {
    if (!task) return;
    patchTask({ layout: { ...task.layout, points } });
  }

  function updatePoints(points: Point2D[], context: EditContext = {}): void {
    if (!task) return;
    patchTask({ layout: { ...task.layout, points } }, context);
  }

  function addPoint(): void {
    if (currentPosition && canAddPoint && task) replacePoints([...task.layout.points, currentPosition]);
  }

  function updateAnchor(axis: keyof Point2D, value: number | null): void {
    if (value == null || !task || task.layout.type !== 'area') return;
    patchTask({
      layout: {
        ...task.layout,
        grid: { ...task.layout.grid, anchor: { ...task.layout.grid.anchor, [axis]: value } }
      }
    });
  }

  function updateOverlap(value: number | null): void {
    if (value == null || !task || task.layout.type !== 'area') return;
    patchTask({ layout: { ...task.layout, grid: { ...task.layout.grid, overlap: value } } });
  }

  function updateZ(field: 'start' | 'end', value: number | null): void {
    if (value == null || !task) return;
    patchTask({ z: { ...task.z, [field]: value } });
  }

  function toggleProfile(profileId: string, checked: boolean): void {
    if (!task) return;
    const profiles = checked
      ? [...new Set([...task.profiles, profileId])]
      : task.profiles.filter((candidate) => candidate !== profileId);
    if (profiles.length) patchTask({ profiles });
  }

  function reorderProfiles(profiles: string[]): void {
    patchTask({ profiles });
  }

  function profileLabel(profileId: string): string {
    return instrument?.imaging.profiles[profileId]?.label || displayName(profileId);
  }

  async function deleteTask(): Promise<void> {
    if (!instrument || !task || disabled) return;
    const request = instrument.removeTasks([task.id]);
    toastError(request);
    try {
      await request;
    } catch {
      return;
    }
    deleteDialogOpen = false;
    await goto(planHref);
  }
</script>

{#snippet profileChip(profileId: string)}
  <Sortable.Item
    item={profileId}
    class="flex h-5 max-w-full min-w-0 items-center rounded-sm border border-line-faint bg-element-hover text-base"
  >
    <Sortable.Handle
      item={profileId}
      {disabled}
      class="flex h-full w-4 shrink-0 cursor-grab touch-none items-center justify-center text-fg-muted/60 active:cursor-grabbing"
    >
      <GripVertical class="size-3" />
    </Sortable.Handle>
    <span class="min-w-0 truncate pr-1.5 pl-0.5 text-fg">{profileLabel(profileId)}</span>
    <button
      type="button"
      class="flex h-full shrink-0 items-center rounded-r px-0.5 text-fg-muted/50 transition-colors hover:text-danger disabled:pointer-events-none disabled:opacity-30"
      disabled={disabled || task?.profiles.length === 1}
      aria-label={`Remove ${profileLabel(profileId)}`}
      title={`Remove ${profileLabel(profileId)}`}
      onclick={() => toggleProfile(profileId, false)}
    >
      <Close class="size-3.5" />
    </button>
  </Sortable.Item>
{/snippet}

{#snippet addProfileButton()}
  <DropdownMenu.Root>
    <DropdownMenu.Trigger
      class={buttonVariants({
        variant: 'ghost',
        size: 'icon-xs',
        class: 'text-fg-muted'
      })}
      disabled={disabled || availableProfiles.length === 0}
      aria-label="Add profile"
      title="Add profile"
    >
      <Plus class="size-3.5" />
    </DropdownMenu.Trigger>
    <DropdownMenu.Content align="start" class="font-normal">
      {#each availableProfiles as profileId (profileId)}
        <DropdownMenu.Item class="text-base" onclick={() => toggleProfile(profileId, true)}>
          {profileLabel(profileId)}
        </DropdownMenu.Item>
      {/each}
    </DropdownMenu.Content>
  </DropdownMenu.Root>
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader
    items={[
      { label: 'Plan', href: planHref },
      { label: taskIndex >= 0 ? `Task ${taskIndex + 1}` : 'Task', title: taskId }
    ]}
  >
    {#snippet trailing()}
      {#if task}
        <span class="text-sm text-fg-muted">{task.layout.type === 'area' ? 'Area' : 'Explicit positions'}</span>
      {/if}
      <Button
        variant="outline"
        size="icon-xs"
        class="text-fg-muted"
        disabled={!task || disabled}
        aria-label="Delete task"
        title="Delete task"
        onclick={() => (deleteDialogOpen = true)}
      >
        <TrashCanOutline class="size-3.5" />
      </Button>
    {/snippet}
  </PageHeader>

  <div class="@container min-h-0 flex-1 overflow-hidden px-4 pb-5">
    {#if !instrument}
      <p class="text-base text-fg-muted">Open this instrument to edit the task.</p>
    {:else if !task}
      <p class="text-base text-fg-muted">This task is no longer in the plan.</p>
    {:else}
      <div class="flex h-full min-h-0 flex-col gap-4">
        <section class="shrink-0 rounded-lg border border-line-muted px-3 py-2" aria-label="Task settings">
          <div class="grid min-w-0 grid-cols-[5rem_minmax(0,1fr)] items-start gap-x-2 gap-y-3">
            <span class="flex h-ui-xs items-center text-base text-fg-muted">Ordering</span>
            <div class="grid min-w-0 gap-2 @min-[38rem]:grid-cols-2">
              <label class="min-w-0">
                <span class="sr-only">Ordering</span>
                <Select
                  size="xs"
                  class="w-full"
                  prefix="Mode"
                  value={task.volume_order}
                  options={volumeOrderOptions}
                  {disabled}
                  onchange={(value) => patchTask({ volume_order: value as VolumeOrder })}
                />
              </label>
              <Select
                size="xs"
                class="w-full"
                prefix="Traversal"
                value={task.traversal}
                options={traversalOptions}
                {disabled}
                onchange={(value) => patchTask({ traversal: value as TileOrder })}
              />
            </div>
            <span class="flex h-ui-xs items-center text-base text-fg-muted">Z range</span>
            <div class="grid min-w-0 gap-2 @min-[38rem]:grid-cols-2">
              <StageNumericField
                stage={instrument.stage}
                axis="z"
                align="right"
                value={task.z.start}
                max={task.z.end}
                prefix="Start"
                suffix={unit.label}
                step={unit.step * unit.scale}
                increment={unit.step * unit.scale}
                bigIncrement={unit.bigStep * unit.scale}
                displayScale={unit.scale}
                decimals={unit.decimals}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateZ('start', value)}
                {disabled}
              />
              <StageNumericField
                stage={instrument.stage}
                axis="z"
                align="right"
                value={task.z.end}
                min={task.z.start}
                prefix="End"
                suffix={unit.label}
                step={unit.step * unit.scale}
                increment={unit.step * unit.scale}
                bigIncrement={unit.bigStep * unit.scale}
                displayScale={unit.scale}
                decimals={unit.decimals}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateZ('end', value)}
                {disabled}
              />
            </div>
            {#if task.layout.type === 'area'}
              <span class="flex h-ui-xs items-center text-base text-fg-muted">Grid</span>
              <div class="grid min-w-0 gap-2 @min-[38rem]:grid-cols-2">
                <StageNumericField
                  stage={instrument.stage}
                  axis="x"
                  align="right"
                  value={task.layout.grid.anchor.x}
                  prefix="X"
                  suffix={unit.label}
                  step={unit.step * unit.scale}
                  increment={unit.step * unit.scale}
                  bigIncrement={unit.bigStep * unit.scale}
                  displayScale={unit.scale}
                  decimals={unit.decimals}
                  oneditstart={() => instrument.edits.hold()}
                  oncommit={(value) => updateAnchor('x', value)}
                  {disabled}
                />
                <StageNumericField
                  stage={instrument.stage}
                  axis="y"
                  align="right"
                  value={task.layout.grid.anchor.y}
                  prefix="Y"
                  suffix={unit.label}
                  step={unit.step * unit.scale}
                  increment={unit.step * unit.scale}
                  bigIncrement={unit.bigStep * unit.scale}
                  displayScale={unit.scale}
                  decimals={unit.decimals}
                  oneditstart={() => instrument.edits.hold()}
                  oncommit={(value) => updateAnchor('y', value)}
                  {disabled}
                />
              </div>
              <span class="flex h-ui-xs items-center text-base text-fg-muted">Overlap</span>
              <div class="grid min-w-0 gap-2 @min-[38rem]:grid-cols-2">
                <NumericField
                  value={task.layout.grid.overlap}
                  min={0}
                  max={0.99}
                  step={0.01}
                  increment={0.01}
                  bigIncrement={0.1}
                  displayScale={0.01}
                  decimals={0}
                  suffix="%"
                  oneditstart={() => instrument.edits.hold()}
                  oncommit={updateOverlap}
                  {disabled}
                />
              </div>
            {/if}
          </div>
        </section>

        <section
          class="flex shrink flex-col gap-1.5 overflow-hidden rounded-lg border border-line-muted"
          aria-labelledby="task-xy-list-heading"
        >
          <div class="grid grid-cols-[minmax(0,1fr)_var(--spacing-ui-xs)] items-center px-3 pt-1">
            <div class="flex min-w-0 items-baseline gap-2">
              <h2 id="task-xy-list-heading" class="shrink-0 text-base text-fg">
                {task.layout.type === 'area' ? 'Boundary' : 'Positions'}
              </h2>
              <span class="truncate text-sm text-fg-muted">
                {#if task.layout.type === 'area'}
                  {pointCount}
                  {pointCount === 1 ? 'point' : 'points'}
                  {#if areaPositionCount != null}
                    · {areaPositionCount} {areaPositionCount === 1 ? 'position' : 'positions'}
                  {/if}
                {:else}
                  {pointCount}
                {/if}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon-xs"
              class="text-fg-muted"
              disabled={disabled || !canAddPoint}
              aria-label="Add current stage position"
              title="Add current stage position"
              onclick={addPoint}
            >
              <Plus class="size-3.5" />
            </Button>
          </div>

          <XYPointList
            points={task.layout.points}
            current={currentPosition}
            minimum={minimumPoints}
            {disabled}
            onchange={updatePoints}
            class="min-h-0 shrink px-3 pb-2"
          />
        </section>

        <section
          class="flex shrink-0 flex-col gap-1.5 rounded-lg border border-line-muted"
          aria-labelledby="task-profiles-section-heading"
        >
          <div class="grid grid-cols-[minmax(0,1fr)_var(--spacing-ui-xs)] items-center px-3 pt-1">
            <h2 id="task-profiles-section-heading" class="text-base text-fg">Profiles</h2>
            {@render addProfileButton()}
          </div>
          <div
            class="flex min-h-5 flex-wrap items-center gap-1.5 px-3 pb-2"
            role="group"
            aria-labelledby="task-profiles-section-heading"
          >
            <Sortable.Root
              items={task.profiles}
              key={(profileId) => profileId}
              onReorder={reorderProfiles}
              item={profileChip}
              layout="flow"
              class="flex flex-wrap items-center gap-1.5"
            />
          </div>
        </section>
      </div>
    {/if}
  </div>
</div>

<Dialog.Root bind:open={deleteDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Delete task</Dialog.Title>
      <Dialog.Description>Delete Task {taskIndex + 1}? This can be restored with Undo.</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" disabled={instrument?.edits.busy} onclick={() => (deleteDialogOpen = false)}>
        Cancel
      </Button>
      <Button variant="danger" loading={instrument?.edits.busy} disabled={!task || disabled} onclick={deleteTask}>
        Delete
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
