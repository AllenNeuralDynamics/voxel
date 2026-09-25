<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Plus } from '$lib/icons';
  import { Button, Select } from '$lib/kit';
  import { createAreaTask, createPositionTask, getVoxelStation, planningFov } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { getRegionSelection } from '$lib/stage/region.svelte';
  import { displayName, toastError } from '$lib/utils';

  const app = getVoxelStation();
  const regionSelection = getRegionSelection();
  const routeParams = $derived({
    stationId: page.params.stationId ?? '',
    instrumentId: page.params.instrumentId ?? ''
  });
  const instrument = $derived(app.instrument?.id === routeParams.instrumentId ? app.instrument : null);
  const preferenceKey = $derived(`${routeParams.stationId}/${routeParams.instrumentId}`);
  const currentPosition = $derived.by(() => {
    const x = instrument?.stage.x.position?.value;
    const y = instrument?.stage.y.position?.value;
    return x != null && y != null && Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  });
  const currentZRange = $derived.by(() => {
    const saved = prefs.plan.defaults.get()[preferenceKey]?.zRange;
    if (saved) return saved;
    const z = instrument?.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });
  const currentProfile = $derived(
    instrument?.activeProfileId ?? Object.keys(instrument?.imaging.profiles ?? {})[0] ?? null
  );
  const currentPlanningFov = $derived(
    currentProfile && instrument ? planningFov(instrument.profileFovs, [currentProfile]) : null
  );
  const areaBounds = $derived.by(() => {
    const saved = prefs.plan.defaults.get()[preferenceKey]?.region;
    if (regionSelection.bounds ?? saved) return regionSelection.bounds ?? saved ?? null;
    const point = currentPosition;
    const fov = currentPlanningFov;
    if (!point || !fov) return null;
    return {
      minX: point.x - fov[0] / 2,
      maxX: point.x + fov[0] / 2,
      minY: point.y - fov[1] / 2,
      maxY: point.y + fov[1] / 2
    };
  });
  const taskNumbers = $derived(new Map(instrument?.plan.map((task, index) => [task.id, index + 1]) ?? []));
  const taskFilterOptions = $derived([
    { value: 'all', label: 'All tasks' },
    ...(instrument?.plan.map((task, index) => ({ value: task.id, label: `Task ${index + 1}` })) ?? [])
  ]);
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const coordinateFormat = new Intl.NumberFormat(undefined, {
    minimumSignificantDigits: 5,
    maximumSignificantDigits: 5,
    useGrouping: false
  });
  const disabled = $derived(!instrument || instrument.mode === 'capture' || instrument.edits.busy);
  const canAddPosition = $derived(!disabled && !!currentPosition && !!currentZRange && !!currentProfile);
  const canAddArea = $derived(!disabled && !!areaBounds && !!currentZRange && !!currentProfile && !!currentPlanningFov);
  let taskFilter = $state('all');
  const selectedTask = $derived(
    taskFilter !== 'all' && instrument?.plan.some((task) => task.id === taskFilter) ? taskFilter : 'all'
  );
  const volumeRows = $derived(
    (instrument?.plannedVolumes ?? [])
      .map((volume, index) => ({ volume, index }))
      .filter(({ volume }) => selectedTask === 'all' || volume.task === selectedTask)
  );

  function formatCoordinate(value: number): string {
    return Number.isFinite(value) ? coordinateFormat.format(value / unit.scale) : '—';
  }

  function profileLabel(profileId: string): string {
    return instrument?.imaging.profiles[profileId]?.label || displayName(profileId);
  }

  async function addAtCurrentPosition() {
    const inst = instrument;
    const point = currentPosition;
    const z = currentZRange;
    const profile = currentProfile;
    if (!inst || !point || !z || !profile || disabled) return;

    const task = createPositionTask([point], profile, z);
    await inst.addTask(task);

    const defaults = prefs.plan.defaults.get();
    if (!defaults[preferenceKey]) {
      prefs.plan.defaults.set({
        ...defaults,
        [preferenceKey]: { zRange: z, overlap: 0.1 }
      });
    }
    if (instrument !== inst) return;
    await goto(
      resolve('/stations/[stationId]/instruments/[instrumentId]/plan/[taskId]', {
        ...routeParams,
        taskId: task.id
      })
    );
  }

  async function addArea() {
    const inst = instrument;
    const bounds = areaBounds;
    const z = currentZRange;
    const profile = currentProfile;
    const fov = currentPlanningFov;
    if (!inst || !bounds || !z || !profile || !fov || disabled) return;

    const overlap = prefs.plan.defaults.get()[preferenceKey]?.overlap ?? 0.1;
    const task = createAreaTask(bounds, fov, overlap, profile, z);
    await inst.addTask(task);

    prefs.plan.defaults.set({
      ...prefs.plan.defaults.get(),
      [preferenceKey]: { region: { ...bounds }, zRange: z, overlap }
    });
    regionSelection.clear();
    if (instrument !== inst) return;
    await goto(
      resolve('/stations/[stationId]/instruments/[instrumentId]/plan/[taskId]', {
        ...routeParams,
        taskId: task.id
      })
    );
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Plan' }]}>
    {#snippet trailing()}
      <Button
        variant="outline"
        size="xs"
        class="w-28"
        disabled={!canAddPosition}
        title="Create a task at the current XY position"
        onclick={() => toastError(addAtCurrentPosition())}
      >
        <Plus class="size-3.5" />
        Position
      </Button>
      <Button
        variant="outline"
        size="xs"
        class="w-28"
        disabled={!canAddArea}
        title="Create a tiled area task"
        onclick={() => toastError(addArea())}
      >
        <Plus class="size-3.5" />
        Area
      </Button>
    {/snippet}
  </PageHeader>
  <div class="min-h-0 flex-1 overflow-y-auto px-4 pb-5">
    {#if instrument}
      <div class="space-y-2">
        {#each instrument.plan as task, index (task.id)}
          <a
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/plan/[taskId]', {
              ...routeParams,
              taskId: task.id
            })}
            class="block rounded-lg border border-line-faint px-3 py-2 text-base text-fg transition-colors hover:bg-element-hover"
          >
            Task {index + 1}
          </a>
        {:else}
          <p class="text-base text-fg-muted">No tasks have been added to this plan.</p>
        {/each}
      </div>

      <section class="mt-5" aria-labelledby="plan-volumes-heading">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-baseline gap-2">
            <h2 id="plan-volumes-heading" class="text-base text-fg">Volumes</h2>
            <span class="text-sm text-fg-muted tabular-nums">
              {volumeRows.length}{#if selectedTask !== 'all'}
                of {instrument.plannedVolumes.length}{/if}
            </span>
          </div>
          {#if instrument.plan.length > 1}
            <Select
              size="xs"
              class="w-40"
              prefix="Task"
              value={selectedTask}
              options={taskFilterOptions}
              onchange={(value) => (taskFilter = value)}
            />
          {/if}
        </div>
        {#if volumeRows.length}
          <div class="space-y-1.5">
            {#each volumeRows as { volume, index } (`${volume.task}:${volume.profile}:${volume.x}:${volume.y}:${index}`)}
              <div
                class="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-x-2 gap-y-1 rounded-lg border border-line-muted px-2.5 py-1.5 transition-colors hover:bg-element-hover/50 @min-[48rem]:grid-cols-[minmax(8rem,1fr)_auto_2rem]"
              >
                <div class="flex min-w-0 items-baseline gap-2">
                  <span class="truncate text-base text-fg">{profileLabel(volume.profile)}</span>
                  <span class="shrink-0 text-sm text-fg-muted">Task {taskNumbers.get(volume.task) ?? '—'}</span>
                </div>
                <div
                  class="col-start-1 row-start-2 flex min-w-0 flex-wrap items-center gap-1 text-sm text-fg-muted tabular-nums @min-[48rem]:col-start-2 @min-[48rem]:row-start-1"
                >
                  <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap">
                    <span class="mr-1 text-fg-faint">X</span>{formatCoordinate(volume.x)}
                  </span>
                  <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap">
                    <span class="mr-1 text-fg-faint">Y</span>{formatCoordinate(volume.y)}
                  </span>
                  <span class="rounded-sm bg-element-bg px-1.5 py-0.5 whitespace-nowrap">
                    <span class="mr-1 text-fg-faint">Z</span>{formatCoordinate(volume.z_start)} – {formatCoordinate(
                      volume.z_end
                    )}
                  </span>
                  <span class="ml-0.5">{unit.label}</span>
                </div>
                <span
                  class="col-start-2 row-start-1 text-right text-sm text-fg-muted tabular-nums @min-[48rem]:col-start-3"
                  title="Volume {index + 1}">{index + 1}</span
                >
              </div>
            {/each}
          </div>
        {:else}
          <p class="py-2 text-base text-fg-muted">No volumes have been resolved for this plan.</p>
        {/if}
      </section>
    {:else}
      <p class="text-base text-fg-muted">Open this instrument to view its plan.</p>
    {/if}
  </div>
</div>
