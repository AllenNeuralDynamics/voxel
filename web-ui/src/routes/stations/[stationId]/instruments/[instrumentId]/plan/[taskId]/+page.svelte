<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Close, Crosshair, GripVertical, Link, LinkOff, Plus, TrashCanOutline } from '$lib/icons';
  import { Button, buttonVariants, Dialog, DropdownMenu, Select } from '$lib/kit';
  import * as Sortable from '$lib/kit/sortable';
  import {
    convexHull,
    type EditContext,
    getVoxelStation,
    type IterationOrder,
    type Point2D,
    pointBounds,
    resizePointsToBounds,
    type TaskPatch,
    type TileOrder,
    type XYMode
  } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { Input as NumericInput, NumericField } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { displayName, toastError } from '$lib/utils';

  import FieldRow from './FieldRow.svelte';
  import Section from './Section.svelte';
  import StageNumericField from './StageNumericField.svelte';

  const app = getVoxelStation();
  const routeParams = $derived({
    stationId: page.params.stationId ?? '',
    instrumentId: page.params.instrumentId ?? ''
  });
  const instrument = $derived(app.instrument?.id === routeParams.instrumentId ? app.instrument : null);
  const taskId = $derived(page.params.taskId ?? '');
  const taskIndex = $derived(instrument?.plan.findIndex((candidate) => candidate.id === taskId) ?? -1);
  const task = $derived(taskIndex < 0 ? undefined : instrument?.plan[taskIndex]);
  const volumeRows = $derived(
    (instrument?.plannedVolumes ?? []).flatMap((volume, index) => (volume.task === taskId ? [{ volume, index }] : []))
  );
  const positionCount = $derived(new Set(volumeRows.map(({ volume }) => `${volume.x}\0${volume.y}`)).size);
  const layoutPoints = $derived(task?.xy.points ?? []);
  const sortablePoints = $derived(layoutPoints.map((point) => ({ key: `${point.x}\0${point.y}`, point })));
  const bounds = $derived(layoutPoints.length ? pointBounds(layoutPoints) : null);
  const currentPosition = $derived.by(() => {
    const x = instrument?.stage.x.position?.value;
    const y = instrument?.stage.y.position?.value;
    return x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y) ? null : { x, y };
  });
  const canAddPoint = $derived(
    !!currentPosition &&
      !!task &&
      !layoutPoints.some((point) => point.x === currentPosition.x && point.y === currentPosition.y)
  );
  const canUseBoundingBox = $derived(
    new Set(layoutPoints.map(({ x }) => x)).size >= 2 && new Set(layoutPoints.map(({ y }) => y)).size >= 2
  );
  const canUseConvexHull = $derived(layoutPoints.length >= 3 && convexHull(layoutPoints).length >= 3);
  const xyModeOptions = $derived.by((): { value: XYMode; label: string }[] => [
    { value: 'explicit_points', label: 'Explicit points' },
    ...(canUseBoundingBox ? [{ value: 'bounding_box' as const, label: 'Bounding box' }] : []),
    ...(canUseConvexHull ? [{ value: 'convex_hull' as const, label: 'Convex hull' }] : [])
  ]);
  const availableProfiles = $derived(
    Object.keys(instrument?.imaging.profiles ?? {}).filter((profileId) => !task?.profiles.includes(profileId))
  );
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const coordinateFormat = new Intl.NumberFormat(undefined, {
    minimumSignificantDigits: 5,
    maximumSignificantDigits: 5,
    useGrouping: false
  });
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
  const iterationOptions: { value: IterationOrder; label: string }[] = [
    { value: 'position_major', label: 'Position first' },
    { value: 'profile_major', label: 'Profile first' }
  ];

  let deleteDialogOpen = $state(false);
  let overlapLink = $state<{ task: string; linked: boolean } | null>(null);
  const overlapLinked = $derived.by(() => {
    if (!task) return false;
    return overlapLink?.task === task.id ? overlapLink.linked : task.xy.overlap.x === task.xy.overlap.y;
  });

  function patchTask(patch: TaskPatch, context: EditContext = {}): void {
    if (!instrument || !task || disabled) return;
    toastError(instrument.updateTask(task.id, patch, context));
  }

  function updateLayoutPoints(points: Point2D[], context: EditContext = {}): void {
    if (!task) return;
    patchTask({ xy: { ...task.xy, points } }, context);
  }

  function addPoint(): void {
    if (currentPosition && canAddPoint) updateLayoutPoints([...layoutPoints, currentPosition]);
  }

  function reorderLayoutPoints(items: { key: string; point: Point2D }[]): void {
    updateLayoutPoints(items.map(({ point }) => point));
  }

  function replaceLayoutPoint(index: number, point: Point2D, context?: EditContext): void {
    updateLayoutPoints(
      layoutPoints.map((currentPoint, pointIndex) => (pointIndex === index ? point : currentPoint)),
      context
    );
  }

  function updateLayoutPoint(index: number, axis: keyof Point2D, value: number, context: EditContext): void {
    const point = layoutPoints[index];
    if (!point || Object.is(point[axis], value)) return;
    replaceLayoutPoint(index, { ...point, [axis]: value }, context);
  }

  function canUseCurrentPoint(index: number): boolean {
    if (!currentPosition) return false;
    const point = layoutPoints[index];
    if (point?.x === currentPosition.x && point.y === currentPosition.y) return false;
    return !layoutPoints.some(
      (candidate, pointIndex) =>
        pointIndex !== index && candidate.x === currentPosition.x && candidate.y === currentPosition.y
    );
  }

  function useCurrentPoint(index: number): void {
    if (currentPosition && canUseCurrentPoint(index)) replaceLayoutPoint(index, { ...currentPosition });
  }

  function removeLayoutPoint(index: number): void {
    const minimum = task?.xy.mode === 'explicit_points' ? 1 : 3;
    if (layoutPoints.length <= minimum) return;
    updateLayoutPoints(layoutPoints.filter((_, pointIndex) => pointIndex !== index));
  }

  function setPointLayout(mode: XYMode): void {
    if (!task || disabled) return;
    if (mode === 'bounding_box' && !canUseBoundingBox) return;
    if (mode === 'convex_hull' && !canUseConvexHull) return;
    patchTask({ xy: { ...task.xy, mode } });
  }

  function updateBound(axis: keyof Point2D, edge: 'min' | 'max', value: number | null): void {
    if (value == null || !task || !bounds || task.xy.mode !== 'bounding_box') return;
    const opposite =
      edge === 'min' ? (axis === 'x' ? bounds.maxX : bounds.maxY) : axis === 'x' ? bounds.minX : bounds.minY;
    if ((edge === 'min' && value >= opposite) || (edge === 'max' && value <= opposite)) return;
    const next = { ...bounds, [`${edge}${axis.toUpperCase()}`]: value };
    patchTask({ xy: { ...task.xy, points: resizePointsToBounds(task.xy.points, next) } });
  }

  function updateOverlap(axis: keyof Point2D, value: number | null): void {
    if (value == null || !task) return;
    const overlap = overlapLinked ? { x: value, y: value } : { ...task.xy.overlap, [axis]: value };
    patchTask({ xy: { ...task.xy, overlap } });
  }

  function toggleOverlapLink(): void {
    if (!task) return;
    const linked = !overlapLinked;
    overlapLink = { task: task.id, linked };
    if (linked && task.xy.overlap.x !== task.xy.overlap.y) {
      patchTask({ xy: { ...task.xy, overlap: { x: task.xy.overlap.x, y: task.xy.overlap.x } } });
    }
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

  function formatCoordinate(value: number): string {
    return Number.isFinite(value) ? coordinateFormat.format(value / unit.scale) : '—';
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

{#snippet coordinate(value: number, label: string, onchange: (value: number, context: EditContext) => void)}
  <div class="flex min-w-0 items-center">
    <NumericInput
      model={{
        value,
        step: unit.step * unit.scale,
        bigStep: unit.bigStep * unit.scale,
        disabled,
        onChange: onchange
      }}
      displayScale={unit.scale}
      decimals={unit.decimals}
      numCharacters={8}
      align="right"
      {disabled}
      aria-label={label}
      class="min-w-0 flex-1 basis-0 px-1 leading-none"
    />
    <span class="pointer-events-none shrink-0 pr-1.5 pl-0.5 font-mono text-fg-muted">{unit.label}</span>
  </div>
{/snippet}

{#snippet positionChip(axis: string, value: string)}
  <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap text-fg-muted">
    <span class="mr-1 text-fg-faint">{axis}</span>{value}
  </span>
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader
    items={[
      { label: 'Plan', href: planHref },
      { label: taskIndex >= 0 ? `Task ${taskIndex + 1}` : 'Task', title: taskId }
    ]}
  >
    {#snippet trailing()}
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
  {#if instrument && task}
    <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      <Section title="XY coverage" class="mx-4 flex flex-col overflow-hidden">
        {#snippet trailing()}
          <Select
            size="xs"
            class="w-42"
            value={task.xy.mode}
            options={xyModeOptions}
            {disabled}
            onchange={(value) => setPointLayout(value as XYMode)}
          />
        {/snippet}

        <div class="flex flex-col gap-3">
          {#if task.xy.mode === 'bounding_box' && bounds}
            <FieldRow label="Minimum">
              <StageNumericField
                stage={instrument.stage}
                axis="x"
                align="right"
                value={bounds.minX}
                max={bounds.maxX}
                prefix="X"
                {unit}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateBound('x', 'min', value)}
                {disabled}
              />
              <StageNumericField
                stage={instrument.stage}
                axis="y"
                align="right"
                value={bounds.minY}
                max={bounds.maxY}
                prefix="Y"
                {unit}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateBound('y', 'min', value)}
                {disabled}
              />
            </FieldRow>
            <FieldRow label="Maximum">
              <StageNumericField
                stage={instrument.stage}
                axis="x"
                align="right"
                value={bounds.maxX}
                min={bounds.minX}
                prefix="X"
                {unit}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateBound('x', 'max', value)}
                {disabled}
              />
              <StageNumericField
                stage={instrument.stage}
                axis="y"
                align="right"
                value={bounds.maxY}
                min={bounds.minY}
                prefix="Y"
                {unit}
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateBound('y', 'max', value)}
                {disabled}
              />
            </FieldRow>
          {:else}
            <div class="mt-3 flex flex-col gap-2">
              <Sortable.Root
                items={sortablePoints}
                key={(item) => item.key}
                onReorder={reorderLayoutPoints}
                layout="vertical"
                flipDuration={120}
                containerClass="max-h-68 min-h-0 shrink"
                class="space-y-2 px-3"
              >
                {#snippet item(item: { key: string; point: Point2D }, index: number)}
                  <Sortable.Item
                    {item}
                    class="focus-within:border-focused grid h-ui-xs grid-cols-[var(--spacing-ui-xs)_minmax(0,16rem)_minmax(0,1fr)_var(--spacing-ui-xs)_var(--spacing-ui-xs)] overflow-hidden rounded border border-control-line bg-element-bg transition-colors hover:bg-element-hover"
                  >
                    {#if task.xy.mode === 'explicit_points'}
                      <Sortable.Handle
                        {item}
                        {disabled}
                        class="flex size-ui-xs shrink-0 cursor-grab touch-none items-center justify-start text-fg-muted active:cursor-grabbing"
                      >
                        <GripVertical class="mx-0.5 size-3.5" />
                      </Sortable.Handle>
                    {:else}
                      <span aria-hidden="true"></span>
                    {/if}

                    <div class="grid min-w-0 cursor-auto grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center">
                      {@render coordinate(item.point.x, `Point ${index + 1} X`, (value, context) =>
                        updateLayoutPoint(index, 'x', value, context)
                      )}
                      <span class="px-0.5 text-fg-muted select-none">,</span>
                      {@render coordinate(item.point.y, `Point ${index + 1} Y`, (value, context) =>
                        updateLayoutPoint(index, 'y', value, context)
                      )}
                    </div>

                    <span aria-hidden="true"></span>

                    <Button
                      variant="ghost"
                      size="icon-xs"
                      class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted focus-visible:ring-offset-0 focus-visible:ring-inset"
                      disabled={disabled || !canUseCurrentPoint(index)}
                      aria-label={`Use current stage position for point ${index + 1}`}
                      title="Use current stage position"
                      onclick={() => useCurrentPoint(index)}
                    >
                      <Crosshair class="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted hover:text-danger focus-visible:ring-offset-0 focus-visible:ring-inset"
                      disabled={disabled || layoutPoints.length <= (task.xy.mode === 'explicit_points' ? 1 : 3)}
                      aria-label={`Delete point ${index + 1}`}
                      title={`Delete point ${index + 1}`}
                      onclick={() => removeLayoutPoint(index)}
                    >
                      <TrashCanOutline class="size-3.5" />
                    </Button>
                  </Sortable.Item>
                {/snippet}
              </Sortable.Root>

              <Button
                variant="outline"
                size="xs"
                class="mx-3 h-ui-xs border-dashed border-line bg-transparent text-fg-muted hover:bg-element-hover"
                disabled={disabled || !canAddPoint}
                onclick={addPoint}
              >
                <Plus class="size-3.5" />
                Add current point
              </Button>
            </div>
          {/if}

          {#if task.xy.mode !== 'explicit_points'}
            <FieldRow label="Overlap" fieldsClass="*:basis-20">
              {#snippet trailing()}
                <button
                  type="button"
                  class={overlapLinked
                    ? 'cursor-pointer text-fg transition-colors'
                    : 'cursor-pointer text-fg-faint transition-colors hover:text-fg'}
                  {disabled}
                  aria-label={overlapLinked ? 'Unlink X and Y overlap' : 'Link X and Y overlap'}
                  title={overlapLinked ? 'X and Y overlap are linked' : 'Link X and Y overlap'}
                  onclick={toggleOverlapLink}
                >
                  {#if overlapLinked}<Link class="size-3" />{:else}<LinkOff class="size-3" />{/if}
                </button>
              {/snippet}
              <NumericField
                value={task.xy.overlap.x}
                min={0}
                max={0.99}
                step={0.01}
                increment={0.01}
                bigIncrement={0.1}
                displayScale={0.01}
                decimals={0}
                align="right"
                prefix="X"
                suffix="%"
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateOverlap('x', value)}
                {disabled}
              />
              <NumericField
                value={task.xy.overlap.y}
                min={0}
                max={0.99}
                step={0.01}
                increment={0.01}
                bigIncrement={0.1}
                displayScale={0.01}
                decimals={0}
                align="right"
                prefix="Y"
                suffix="%"
                oneditstart={() => instrument.edits.hold()}
                oncommit={(value) => updateOverlap('y', value)}
                {disabled}
              />
            </FieldRow>
          {/if}
        </div>
      </Section>

      <Section title="Z coverage" class="mx-4">
        <FieldRow label="Range">
          <StageNumericField
            stage={instrument.stage}
            axis="z"
            align="right"
            value={task.z.start}
            max={task.z.end}
            prefix="Start"
            {unit}
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
            {unit}
            oneditstart={() => instrument.edits.hold()}
            oncommit={(value) => updateZ('end', value)}
            {disabled}
          />
        </FieldRow>
      </Section>

      <Section title="Profiles" class="mx-4">
        {#snippet trailing()}
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
        <Sortable.Root
          items={task.profiles}
          key={(profileId) => profileId}
          onReorder={reorderProfiles}
          layout="flow"
          class="flex min-h-5 flex-wrap items-center gap-1.5 px-3"
        >
          {#snippet item(profileId: string)}
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
                disabled={disabled || task.profiles.length === 1}
                aria-label={`Remove ${profileLabel(profileId)}`}
                title={`Remove ${profileLabel(profileId)}`}
                onclick={() => toggleProfile(profileId, false)}
              >
                <Close class="size-3.5" />
              </button>
            </Sortable.Item>
          {/snippet}
        </Sortable.Root>
      </Section>

      <Section title="Ordering" class="mx-4">
        <div class="flex flex-col gap-3">
          <FieldRow label="Mode">
            <Select
              size="xs"
              class="w-full"
              value={task.iteration}
              options={iterationOptions}
              {disabled}
              onchange={(value) => patchTask({ iteration: value as IterationOrder })}
            />
          </FieldRow>
          <FieldRow label="Path">
            <Select
              size="xs"
              class="w-full"
              value={task.traversal}
              options={traversalOptions}
              {disabled}
              onchange={(value) => patchTask({ traversal: value as TileOrder })}
            />
          </FieldRow>
        </div>
      </Section>

      <section
        class="mx-4 flex min-h-40 flex-1 flex-col overflow-hidden rounded-t-lg border-x border-t border-line-muted bg-element-bg/50"
        aria-labelledby="task-volumes-heading"
      >
        <header class="flex shrink-0 items-center justify-between gap-3 px-3">
          <h2 id="task-volumes-heading" class="my-2.5 text-base text-fg">Volumes</h2>
          <span
            class="flex h-4 shrink-0 overflow-hidden rounded-sm border border-line-muted text-sm leading-none tabular-nums"
            aria-label={`${positionCount} positions, ${volumeRows.length} volumes`}
            title={`${positionCount} positions · ${volumeRows.length} volumes`}
          >
            <span class="flex min-w-7 items-center justify-center bg-element-bg px-1.5 text-fg-muted">
              {positionCount}
            </span>
            <span
              class="flex min-w-7 items-center justify-center border-l border-line-faint bg-element-hover px-1.5 text-fg"
            >
              {volumeRows.length}
            </span>
          </span>
        </header>
        {#if volumeRows.length}
          <div class="min-h-0 flex-1 divide-y divide-line-muted overflow-y-auto border-t border-line-faint pb-2">
            {#each volumeRows as { volume, index } (`${volume.profile}:${volume.x}:${volume.y}:${index}`)}
              <div
                class="flex min-w-0 items-center gap-1.5 py-1.5 pr-3 pl-2 hover:bg-element-hover/50"
                aria-label={`Volume ${index + 1}, ${profileLabel(volume.profile)}, X ${formatCoordinate(volume.x)} ${unit.label}, Y ${formatCoordinate(volume.y)} ${unit.label}, Z ${formatCoordinate(volume.z_start)} to ${formatCoordinate(volume.z_end)} ${unit.label}`}
              >
                <div class="flex shrink-0 items-center gap-1 text-sm tabular-nums">
                  {@render positionChip('X', formatCoordinate(volume.x))}
                  {@render positionChip('Y', formatCoordinate(volume.y))}
                  {@render positionChip('Z', `${formatCoordinate(volume.z_start)} – ${formatCoordinate(volume.z_end)}`)}
                </div>
                <span
                  class="min-w-20 truncate rounded-sm bg-element-bg/40 px-1.5 py-0.5 whitespace-nowrap text-fg-muted"
                  title={profileLabel(volume.profile)}
                >
                  {profileLabel(volume.profile)}
                </span>
                <span class="ml-auto w-8 shrink-0 text-right text-sm text-fg-muted tabular-nums">
                  {index + 1}
                </span>
              </div>
            {/each}
          </div>
        {:else}
          <p class="min-h-0 flex-1 overflow-y-auto border-t border-line-faint px-3 py-4 text-base text-fg-muted">
            No volumes have been resolved for this task.
          </p>
        {/if}
      </section>
    </div>
  {:else if !instrument}
    <p class="min-h-0 flex-1 px-4 pb-5 text-base text-fg-muted">Open this instrument to edit the task.</p>
  {:else}
    <p class="min-h-0 flex-1 px-4 pb-5 text-base text-fg-muted">This task is no longer in the plan.</p>
  {/if}
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
