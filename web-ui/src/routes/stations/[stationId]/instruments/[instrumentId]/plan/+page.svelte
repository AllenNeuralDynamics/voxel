<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { ArrowRight, GripVertical, Plus } from '$lib/icons';
  import { Button } from '$lib/kit';
  import * as Sortable from '$lib/kit/sortable';
  import { type AcquisitionTask, createAreaTask, createPositionTask, getVoxelStation, planningFov } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { planOverlap, prefs } from '$lib/prefs';
  import { getRegionSelection } from '$lib/stage/region.svelte';
  import { toastError } from '$lib/utils';

  const taskRoute = '/stations/[stationId]/instruments/[instrumentId]/plan/[taskId]';

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
  const disabled = $derived(!instrument || instrument.mode === 'capture' || instrument.edits.busy);
  const canAddPosition = $derived(!disabled && !!currentPosition && !!currentZRange && !!currentProfile);
  const canAddArea = $derived(!disabled && !!areaBounds && !!currentZRange && !!currentProfile && !!currentPlanningFov);
  const taskVolumeRows = $derived.by(() => {
    const rows = new SvelteMap<string, { x: number; y: number }[]>();
    for (const volume of instrument?.plannedVolumes ?? []) {
      const taskRows = rows.get(volume.task) ?? [];
      taskRows.push(volume);
      rows.set(volume.task, taskRows);
    }
    return rows;
  });

  function layoutLabel(task: AcquisitionTask): string {
    if (task.xy.mode === 'explicit_points') return 'Explicit points';
    if (task.xy.mode === 'bounding_box') return 'Bounding box';
    return 'Convex hull';
  }

  function reorderTasks(tasks: AcquisitionTask[]): void {
    if (!instrument || disabled) return;
    toastError(instrument.reorderTasks(tasks.map(({ id }) => id)));
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
        [preferenceKey]: { zRange: z, overlap: { x: 0.1, y: 0.1 } }
      });
    }
    if (instrument !== inst) return;
    await goto(resolve(taskRoute, { ...routeParams, taskId: task.id }));
  }

  async function addArea() {
    const inst = instrument;
    const bounds = areaBounds;
    const z = currentZRange;
    const profile = currentProfile;
    const fov = currentPlanningFov;
    if (!inst || !bounds || !z || !profile || !fov || disabled) return;

    const overlap = planOverlap(prefs.plan.defaults.get()[preferenceKey]?.overlap);
    const task = createAreaTask(bounds, overlap, profile, z);
    await inst.addTask(task);

    prefs.plan.defaults.set({
      ...prefs.plan.defaults.get(),
      [preferenceKey]: { region: { ...bounds }, zRange: z, overlap }
    });
    regionSelection.clear();
    if (instrument !== inst) return;
    await goto(resolve(taskRoute, { ...routeParams, taskId: task.id }));
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
  <div class="min-h-0 flex-1 overflow-hidden px-4 pb-5">
    {#if instrument}
      {#if instrument.plan.length}
        <Sortable.Root
          items={instrument.plan}
          key={(task) => task.id}
          onReorder={reorderTasks}
          layout="vertical"
          containerClass="h-full"
          class="space-y-2"
        >
          {#snippet item(task: AcquisitionTask, index: number)}
            {@const rows = taskVolumeRows.get(task.id) ?? []}
            {@const positionCount = new Set(rows.map((volume) => `${volume.x}\0${volume.y}`)).size}
            <Sortable.Item
              item={task}
              class="flex h-ui-lg items-center gap-1.5 rounded-md border border-line-muted/80 px-1 text-fg-muted transition-colors hover:bg-element-hover/50"
            >
              <Sortable.Handle
                item={task}
                {disabled}
                class="flex shrink-0 cursor-grab touch-none items-center justify-center active:cursor-grabbing"
              >
                <GripVertical class="size-3.5" />
              </Sortable.Handle>
              <a
                href={resolve(taskRoute, { ...routeParams, taskId: task.id })}
                class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 transition-colors group-hover:bg-element-hover/50"
                aria-label={`Open Task ${index + 1}`}
              >
                <span class="shrink-0 text-base text-fg">Task {index + 1}</span>
                <span class="min-w-0 flex-1"></span>
                <span class="flex h-4 shrink-0 items-center rounded-sm bg-element-bg px-1.5 text-sm leading-none">
                  {layoutLabel(task)}
                </span>
                <span
                  class="flex h-4 shrink-0 overflow-hidden rounded-sm border border-line-faint text-sm leading-none tabular-nums"
                  aria-label={`${positionCount} positions, ${rows.length} volumes`}
                  title={`${positionCount} positions · ${rows.length} volumes`}
                >
                  <span class="flex min-w-7 items-center justify-center bg-element-bg px-1.5 text-fg-muted">
                    {positionCount}
                  </span>
                  <span
                    class="flex min-w-7 items-center justify-center border-l border-line-faint bg-element-hover px-1.5 text-fg"
                  >
                    {rows.length}
                  </span>
                </span>
                <ArrowRight class="size-4 shrink-0 text-fg-muted" aria-hidden="true" />
              </a>
            </Sortable.Item>
          {/snippet}
        </Sortable.Root>
      {:else}
        <p class="text-base text-fg-muted">No tasks have been added to this plan.</p>
      {/if}
    {:else}
      <p class="text-base text-fg-muted">Open this instrument to view its plan.</p>
    {/if}
  </div>
</div>
