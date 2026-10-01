<script lang="ts">
  import type Konva from 'konva';
  import { untrack } from 'svelte';
  import { Group } from 'svelte-konva';

  import { Brush, CenterFocus, Crosshair, FitToScreen, Plus, Stop } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import {
    createAreaTask,
    createPositionTask,
    getVoxelStation,
    NumericModel,
    type PlannedVolume,
    planningFov
  } from '$lib/model';
  import { planOverlap, prefs } from '$lib/prefs';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { formatSpatialDistance, formatSpatialValue } from '$lib/spatial-units';
  import { themes } from '$lib/themes/manager.svelte';
  import { displayName, pref, toastError } from '$lib/utils';

  import Fov from './Fov.svelte';
  import type { Bounds, Point, Viewport } from './geometry';
  import { Tasks } from './plan';
  import Position from './Position.svelte';
  import { getRegionSelection } from './region.svelte';
  import Routing from './Routing.svelte';
  import RoutingRegions from './RoutingRegions.svelte';
  import StageCanvas from './StageCanvas.svelte';

  let { viewport = $bindable(null) }: { viewport?: Viewport | null } = $props();

  const app = getVoxelStation();
  const regionSelection = getRegionSelection();
  const routingRegionsVisible = pref('stage:routing-regions-visible', true);
  let tasksLayer = $state<Tasks>();
  let taskChooser = $state.raw<{ screen: Point; tasks: { id: string; order: number }[] } | null>(null);
  let editingTaskId = $state<string | null>(null);
  let editingSessionId: string | null = null;
  const previews = getPreviewContext();
  const routingVisibility = pref<Record<string, boolean>>('stage:routing-visible', {});
  const taskColors = pref<Record<string, Partial<Record<'x' | 'y', string>>>>('stage:task-colors', {});
  const preview = $derived(previews.current);
  const instrument = $derived(app.instrument);
  const stage = $derived(instrument?.stage);
  const stageBounds = $derived(stage?.bounds(true));
  const travelBounds = $derived(stage?.bounds(false));
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
  const position = $derived.by(() => {
    const x = stage?.x.position?.value;
    const y = stage?.y.position?.value;
    return x == null || y == null ? null : { x, y };
  });
  const areaProfile = $derived(
    instrument?.activeProfileId ?? Object.keys(instrument?.imaging.profiles ?? {})[0] ?? null
  );
  const areaFov = $derived(areaProfile && instrument ? planningFov(instrument.profileFovs, [areaProfile]) : null);
  const areaZRange = $derived.by(() => {
    if (!instrument) return null;
    const key = `${instrument.stationId}/${instrument.id}`;
    const saved = prefs.plan.defaults.get()[key]?.zRange;
    if (saved) return saved;
    const z = instrument.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });
  const editingTask = $derived.by(() => {
    if (!editingTaskId) return null;
    return instrument?.plan.find(({ id }) => id === editingTaskId) ?? null;
  });
  function taskTargets(volumes: ReturnType<Tasks['destinations']>): { id: string; order: number }[] {
    const result: { id: string; order: number }[] = [];
    for (const volume of volumes) {
      if (result.some(({ id }) => id === volume.task)) continue;
      const order = volume.taskOrder ?? (instrument?.plan.findIndex(({ id }) => id === volume.task) ?? -1) + 1;
      if (order > 0) result.push({ id: volume.task, order });
    }
    return result;
  }
  const commandedTarget = $derived.by(() => {
    const target = stage?.target;
    if (!target || !position) return null;
    const x = target.x ?? position.x;
    const y = target.y ?? position.y;
    // Match Stage's arrival tolerance, considering only the displayed axes.
    return Math.abs(x - position.x) > 0.5 || Math.abs(y - position.y) > 0.5 ? { x, y } : null;
  });
  const fov = $derived(stage?.fov ? { width: stage.fov[0], height: stage.fov[1] } : null);

  const routingPalettes = {
    light: ['#0369a1', '#a16207', '#7e22ce', '#047857'],
    dark: ['#7dd3fc', '#fcd34d', '#d8b4fe', '#6ee7b7']
  };

  type RoutingSide = 'lower' | 'upper';

  /** Map selected routing sides to two colors for one axis or four for both. */
  export function routingColor(mode: 'light' | 'dark', x?: RoutingSide, y?: RoutingSide): string | undefined {
    if (x === undefined && y === undefined) return;
    const index = (x === 'upper' ? 1 : 0) + (y === 'upper' ? (x === undefined ? 1 : 2) : 0);
    return routingPalettes[mode][index];
  }
  const routingSplits = $derived(
    Array.from(instrument?.routingDimensions.values() ?? []).flatMap((dimension) =>
      dimension.axis && dimension.model instanceof NumericModel && Number.isFinite(dimension.model.value)
        ? [
            {
              model: dimension.model,
              threshold: dimension.model.value,
              axis: dimension.axis,
              id: dimension.id,
              label: displayName(dimension.id),
              lower: dimension.routeLabel('lower'),
              upper: dimension.routeLabel('upper')
            }
          ]
        : []
    )
  );
  const colorGroups = $derived(
    (['x', 'y'] as const)
      .map((axis) => ({
        axis,
        dimensions: Array.from(instrument?.routingDimensions.values() ?? []).filter(
          (dimension) => dimension.axis === axis
        )
      }))
      .filter(({ dimensions }) => dimensions.length > 0)
  );
  const colorSplits = $derived.by(() => {
    const selected = instrument ? taskColors.get()[`${instrument.stationId}/${instrument.id}`] : undefined;
    return {
      x: routingSplits.find((split) => split.axis === 'x' && split.id === selected?.x),
      y: routingSplits.find((split) => split.axis === 'y' && split.id === selected?.y)
    };
  });
  const routingRegions = $derived.by(() => {
    if (!stageBounds) return [];
    const { x, y } = colorSplits;
    if (!x && !y) return [];
    const edges = (min: number, max: number, threshold?: number) =>
      threshold === undefined ? [min, max] : [min, Math.max(min, Math.min(max, threshold)), max];
    const xs = edges(stageBounds.minX, stageBounds.maxX, x?.threshold);
    const ys = edges(stageBounds.minY, stageBounds.maxY, y?.threshold);
    const regions = [];
    for (let j = 0; j < ys.length - 1; j++) {
      for (let i = 0; i < xs.length - 1; i++) {
        if (xs[i + 1] <= xs[i] || ys[j + 1] <= ys[j]) continue;
        const color = routingColor(
          themes.resolvedMode,
          x ? (i === 0 ? 'lower' : 'upper') : undefined,
          y ? (j === 0 ? 'lower' : 'upper') : undefined
        );
        if (!color) continue;
        regions.push({
          bounds: { minX: xs[i], maxX: xs[i + 1], minY: ys[j], maxY: ys[j + 1] },
          color
        });
      }
    }
    return regions;
  });

  function taskColor(volume: PlannedVolume): string | undefined {
    const x = colorSplits.x && volume.routes[colorSplits.x.id];
    const y = colorSplits.y && volume.routes[colorSplits.y.id];
    if (colorSplits.x && x !== 'lower' && x !== 'upper') return;
    if (colorSplits.y && y !== 'lower' && y !== 'upper') return;
    return routingColor(
      themes.resolvedMode,
      x === 'lower' || x === 'upper' ? x : undefined,
      y === 'lower' || y === 'upper' ? y : undefined
    );
  }

  function clampPosition(point: Point): Point {
    if (!travelBounds) return point;
    return {
      x: Math.max(travelBounds.minX, Math.min(travelBounds.maxX, point.x)),
      y: Math.max(travelBounds.minY, Math.min(travelBounds.maxY, point.y))
    };
  }

  function withinTravelBounds(point: Point): boolean {
    return (
      !travelBounds ||
      (point.x >= travelBounds.minX &&
        point.x <= travelBounds.maxX &&
        point.y >= travelBounds.minY &&
        point.y <= travelBounds.maxY)
    );
  }

  function goToPosition(point: Point) {
    if (!stage || !travelBounds) return;
    toastError(stage.moveTo(clampPosition(point)));
  }

  function handleStageClick(hits: readonly Konva.Shape[], screen: Point): void {
    if (hits.some((hit) => hit.hasName('task-geometry'))) return;
    const tasks = taskTargets(tasksLayer?.destinations(hits) ?? []);
    if (tasks.length === 1) {
      taskChooser = null;
      editingTaskId = tasks[0].id;
    } else if (tasks.length > 1) {
      taskChooser = { screen, tasks };
    } else {
      taskChooser = null;
      editingTaskId = null;
      regionSelection.clear();
    }
  }

  function chooseTask(taskId: string): void {
    taskChooser = null;
    editingTaskId = taskId;
  }

  function stopEditing(): void {
    taskChooser = null;
    editingTaskId = null;
  }

  async function createTaskInRegion(bounds: Bounds) {
    const inst = instrument;
    const profile = areaProfile;
    const fov = areaFov;
    const z = areaZRange;
    if (!inst || !profile || !fov || !z || inst.mode === 'capture' || inst.edits.busy) return;

    const preferenceKey = `${inst.stationId}/${inst.id}`;
    const overlap = planOverlap(prefs.plan.defaults.get()[preferenceKey]?.overlap);
    const task = createAreaTask(bounds, overlap, profile, z);
    await inst.addTask(task);
    prefs.plan.defaults.set({
      ...prefs.plan.defaults.get(),
      [preferenceKey]: { region: { ...bounds }, zRange: z, overlap }
    });
    regionSelection.clear();
    if (instrument !== inst) return;
    editingTaskId = task.id;
  }

  async function createTaskAtPosition(point: Point) {
    const inst = instrument;
    const profile = areaProfile;
    const z = areaZRange;
    if (!inst || !profile || !z || inst.mode === 'capture' || inst.edits.busy) return;

    const task = createPositionTask([point], profile, z);
    await inst.addTask(task);
    const preferenceKey = `${inst.stationId}/${inst.id}`;
    const defaults = prefs.plan.defaults.get();
    if (!defaults[preferenceKey]) {
      prefs.plan.defaults.set({
        ...defaults,
        [preferenceKey]: { zRange: z, overlap: { x: 0.1, y: 0.1 } }
      });
    }
    if (instrument === inst) editingTaskId = task.id;
  }

  $effect(() => {
    const sessionId = instrument?.sessionId ?? null;
    if (sessionId === editingSessionId) return;
    editingSessionId = sessionId;
    editingTaskId = null;
    taskChooser = null;
  });

  $effect(() => {
    const taskId = editingTaskId;
    const taskExists = !taskId || !!instrument?.plan.some(({ id }) => id === taskId);
    if (!taskExists) untrack(stopEditing);
  });

  function scaleBar(scale: number, width: number) {
    const targetUm = (width * 0.2) / scale;
    const barUm = NICE_STEPS.findLast((step) => step <= targetUm) ?? NICE_STEPS[0];
    return { barPx: barUm * scale, label: barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm` };
  }
</script>

{#snippet movementAction(label: string, target: Point, preview: (point: Point | null) => void)}
  <ContextMenu.Item
    onpointerenter={() => preview(target)}
    onpointerleave={() => preview(null)}
    onfocus={() => preview(target)}
    onblur={() => preview(null)}
    onSelect={() => goToPosition(target)}
  >
    {label}
  </ContextMenu.Item>
{/snippet}

{#if instrument && stageBounds && stage}
  <StageCanvas
    bounds={stageBounds}
    orientation={stage.orientation}
    bind:viewport
    bind:marquee={() => regionSelection.bounds, (bounds) => regionSelection.setBounds(bounds)}
    onstageclick={(_, hits, screen) => handleStageClick(hits, screen)}
    onescape={stopEditing}
    onmenuopen={() => (taskChooser = null)}
  >
    {#snippet overlay(view, width, height, cursor)}
      {#if taskChooser}
        {@const chooserHeight = 29 + taskChooser.tasks.length * 30}
        <div
          class="canvas-overlay-halo absolute z-20 w-32 overflow-hidden rounded-md border border-line-muted bg-floating py-1"
          style:left={`${Math.max(8, Math.min(taskChooser.screen.x + 8, width - 136))}px`}
          style:top={`${Math.max(8, Math.min(taskChooser.screen.y + 8, height - chooserHeight - 8))}px`}
          role="menu"
          aria-label="Edit task"
        >
          <div class="px-2 py-1 text-sm text-fg-muted">Edit task</div>
          {#each taskChooser.tasks as task (task.id)}
            <button
              type="button"
              class="flex h-7 w-full items-center px-2 text-left text-base text-fg hover:bg-element-hover"
              role="menuitem"
              onclick={() => chooseTask(task.id)}
            >
              Task {task.order}
            </button>
          {/each}
        </div>
      {/if}
      {#if cursor}
        {@const inBounds =
          !travelBounds ||
          (cursor.x >= travelBounds.minX &&
            cursor.x <= travelBounds.maxX &&
            cursor.y >= travelBounds.minY &&
            cursor.y <= travelBounds.maxY)}
        <div
          class="canvas-overlay-halo pointer-events-none absolute bottom-4 left-4 z-10 flex gap-2 font-mono tabular-nums {inBounds
            ? 'text-fg-muted'
            : 'text-fg-faint'}"
        >
          <span>X {formatSpatialValue(cursor.x, prefs.spatialUnit.get())}</span>
          <span>Y {formatSpatialDistance(cursor.y, prefs.spatialUnit.get())}</span>
          {#if !inBounds}<span>· out of range</span>{/if}
        </div>
      {/if}
      {@const bar = scaleBar(view.scale, width)}
      <div
        class="canvas-overlay-halo pointer-events-none absolute right-4 bottom-4 z-10 flex flex-col items-end gap-0.5"
      >
        <span class="font-mono text-fg-muted">{bar.label}</span>
        <div class="h-1 rounded-full bg-fg-muted" style:width="{bar.barPx}px"></div>
      </div>
    {/snippet}
    {#snippet menu(selection, taskTargets, goToTargets, fitTargets, center, fitBounds, previewDestination)}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger><Plus width="14" height="14" />Add task</ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
          <ContextMenu.Item
            disabled={instrument.mode === 'capture' ||
              instrument.edits.busy ||
              stage.anyMoving ||
              !position ||
              !areaProfile ||
              !areaZRange}
            onSelect={() => position && toastError(createTaskAtPosition(position))}
          >
            Current stage position
          </ContextMenu.Item>
          <ContextMenu.Item
            disabled={instrument.mode === 'capture' ||
              instrument.edits.busy ||
              !areaProfile ||
              !areaZRange ||
              !withinTravelBounds(selection.point)}
            onSelect={() => toastError(createTaskAtPosition(selection.point))}
          >
            Clicked position
          </ContextMenu.Item>
          {#each taskTargets as target (target.id)}
            <ContextMenu.Item
              disabled={instrument.mode === 'capture' ||
                instrument.edits.busy ||
                !areaProfile ||
                !areaZRange ||
                !withinTravelBounds(target.point)}
              onSelect={() => toastError(createTaskAtPosition(target.point))}
            >
              {target.label}
            </ContextMenu.Item>
          {/each}
          {#if selection.region}
            {@const selectedRegion = selection.region}
            <ContextMenu.Item
              disabled={instrument.mode === 'capture' ||
                instrument.edits.busy ||
                !areaProfile ||
                !areaFov ||
                !areaZRange}
              onSelect={() => toastError(createTaskInRegion(selectedRegion))}
            >
              Selected region
            </ContextMenu.Item>
          {/if}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
      {#if stage.anyMoving}
        <ContextMenu.Item variant="destructive" onSelect={() => toastError(stage.halt())}>
          <Stop width="14" height="14" />
          Halt
        </ContextMenu.Item>
      {:else}
        <ContextMenu.Sub>
          <ContextMenu.SubTrigger><Crosshair width="14" height="14" />Go to</ContextMenu.SubTrigger>
          <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
            {@render movementAction('Clicked position', clampPosition(selection.point), previewDestination)}
            {#each goToTargets as target (target.id)}
              {@render movementAction(target.label, clampPosition(target.point), previewDestination)}
            {/each}
          </ContextMenu.SubContent>
        </ContextMenu.Sub>
      {/if}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger><FitToScreen width="14" height="14" />Fit</ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
          <ContextMenu.Item onSelect={() => fitBounds(stageBounds)}>Stage</ContextMenu.Item>
          {#each fitTargets as target (target.id)}
            <ContextMenu.Item onSelect={() => fitBounds(target.bounds)}>{target.label}</ContextMenu.Item>
          {/each}
          {#if selection.region}
            {@const selectedRegion = selection.region}
            <ContextMenu.Item onSelect={() => fitBounds(selectedRegion)}>Selected region</ContextMenu.Item>
          {/if}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
      {#if position && fov}
        <ContextMenu.Item onSelect={() => center(position)}>
          <CenterFocus width="14" height="14" />
          Recenter on live
        </ContextMenu.Item>
      {/if}
      {#if colorGroups.length}
        {@const key = `${instrument.stationId}/${instrument.id}`}
        <ContextMenu.Sub>
          <ContextMenu.SubTrigger><Brush width="14" height="14" />Task colors</ContextMenu.SubTrigger>
          <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
            {#each colorGroups as { axis, dimensions }, index (axis)}
              {@const selected = taskColors.get()[key]?.[axis] ?? ''}
              {#if index}<ContextMenu.Separator />{/if}
              <ContextMenu.RadioGroup
                aria-label={`${axis.toUpperCase()} split`}
                value={dimensions.some((dimension) => dimension.id === selected) ? selected : ''}
                onValueChange={(value) =>
                  taskColors.set({
                    ...taskColors.get(),
                    [key]: { ...taskColors.get()[key], [axis]: value }
                  })}
              >
                <ContextMenu.GroupHeading>{axis.toUpperCase()} split</ContextMenu.GroupHeading>
                <ContextMenu.RadioItem value="" closeOnSelect={false}>None</ContextMenu.RadioItem>
                {#each dimensions as dimension (dimension.id)}
                  <ContextMenu.RadioItem value={dimension.id} closeOnSelect={false}>
                    {displayName(dimension.id)}
                  </ContextMenu.RadioItem>
                {/each}
              </ContextMenu.RadioGroup>
            {/each}
          </ContextMenu.SubContent>
        </ContextMenu.Sub>
      {/if}
    {/snippet}
    <RoutingRegions
      regions={routingRegions}
      bind:visible={() => routingRegionsVisible.get(), (value) => routingRegionsVisible.set(value)}
    />
    <Fov {preview} bind:visible={() => prefs.stage.liveVisible.get(), (value) => prefs.stage.liveVisible.set(value)} />
    <Tasks bind:this={tasksLayer} {instrument} editingTask={editingTask?.id ?? null} fill={taskColor} />
    <Group>
      {#each routingSplits as rule, index (rule.model)}
        {@const visibilityKey = `${instrument.stationId}/${instrument.id}/${rule.id}`}
        <Routing
          {rule}
          {index}
          color={themes.resolvedMode === 'light' ? '#52525b' : '#d4d4d8'}
          disabled={rule.model.disabled}
          resolveThreshold={(value) => rule.model.resolve(value)}
          onedit={({ phase, threshold }) => {
            if (phase === 'start') rule.model.beginEdit();
            else if (phase === 'move') rule.model.patch(threshold, { throttled: true });
            else rule.model.endEdit(threshold);
          }}
          haloColor={themes.resolvedMode === 'light' ? '#ffffff' : '#18181b'}
          bind:visible={
            () => routingVisibility.get()[visibilityKey] ?? true,
            (visible) => routingVisibility.set({ ...routingVisibility.get(), [visibilityKey]: visible })
          }
          formatDistance={(value) => formatSpatialDistance(value, prefs.spatialUnit.get())}
        />
      {/each}
    </Group>
    <Position {position} {fov} target={commandedTarget} constrain={clampPosition} />
  </StageCanvas>
{:else}
  <div class="flex h-full items-center justify-center text-fg-muted">Waiting for stage limits…</div>
{/if}

<style>
  .canvas-overlay-halo {
    filter: drop-shadow(0 1px 1px color-mix(in oklch, var(--color-canvas) 90%, transparent))
      drop-shadow(0 0 2px color-mix(in oklch, var(--color-canvas) 75%, transparent));
  }
</style>
