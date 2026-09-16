<script lang="ts">
  import { Group } from 'svelte-konva';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getTaskSelection } from '$lib/grid/selection.svelte';
  import { BoxSelect, Brush, CenterFocus, Crosshair, FitToScreen, Stop } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { getVoxelStation, NumericModel, type TaskTile } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { formatSpatialDistance, formatSpatialValue } from '$lib/spatial-units';
  import { themes } from '$lib/themes/manager.svelte';
  import { displayName, pref, toastError } from '$lib/utils';

  import { routingColor } from './colors';
  import Fov from './Fov.svelte';
  import type { Bounds, Point, Viewport } from './geometry';
  import Position from './Position.svelte';
  import Routing from './Routing.svelte';
  import RoutingRegions from './RoutingRegions.svelte';
  import StageCanvas from './StageCanvas.svelte';
  import Tasks from './Tasks.svelte';

  let { viewport = $bindable(null) }: { viewport?: Viewport | null } = $props();

  const app = getVoxelStation();
  const taskSelection = getTaskSelection();
  const tasksVisible = pref('stage:tasks-visible', true);
  const routingRegionsVisible = pref('stage:routing-regions-visible', true);
  let fovLayer = $state<Fov>();
  let positionLayer = $state<Position>();
  let tasksLayer = $state<Tasks>();
  let marquee = $state<Bounds | null>(null);
  let menuTasks = $state.raw<ReturnType<Tasks['destinations']>>([]);
  let menuGrid = $state.raw<Point | undefined>();
  const previews = getPreviewContext();
  const routingVisibility = pref<Record<string, boolean>>('stage:routing-visible', {});
  const taskColors = pref<Record<string, Partial<Record<'x' | 'y', string>>>>('stage:task-colors', {});
  const preview = $derived(previews.current);
  const instrument = $derived(app.instrument);
  const stage = $derived(instrument?.stage);
  const stageBounds = $derived(stage?.bounds(true));
  const travelBounds = $derived(stage?.bounds(false));
  const planAddHref = $derived(
    instrument
      ? resolve('/stations/[stationId]/instruments/[instrumentId]/plan/add', {
          stationId: instrument.stationId,
          instrumentId: instrument.id
        })
      : ''
  );
  const definingRegion = $derived(page.url.pathname === planAddHref);
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
  const position = $derived.by(() => {
    const x = stage?.x.position?.value;
    const y = stage?.y.position?.value;
    return x == null || y == null ? null : { x, y };
  });
  const commandedTarget = $derived.by(() => {
    const target = stage?.target;
    if (!target || !position) return null;
    const x = target.x ?? position.x;
    const y = target.y ?? position.y;
    // Match Stage's arrival tolerance, considering only the displayed axes.
    return Math.abs(x - position.x) > 0.5 || Math.abs(y - position.y) > 0.5 ? { x, y } : null;
  });
  const fov = $derived(stage?.fov ? { width: stage.fov[0], height: stage.fov[1] } : null);
  const liveBounds = $derived(
    position && fov
      ? {
          minX: position.x - fov.width / 2,
          maxX: position.x + fov.width / 2,
          minY: position.y - fov.height / 2,
          maxY: position.y + fov.height / 2
        }
      : null
  );
  const taskBounds = $derived.by(() => {
    let result: Bounds | null = null;
    for (const tile of instrument?.taskTiles ?? []) {
      if (![tile.x, tile.y, tile.w, tile.h].every(Number.isFinite) || tile.w <= 0 || tile.h <= 0) continue;
      const bounds = {
        minX: tile.x - tile.w / 2,
        maxX: tile.x + tile.w / 2,
        minY: tile.y - tile.h / 2,
        maxY: tile.y + tile.h / 2
      };
      result = result
        ? {
            minX: Math.min(result.minX, bounds.minX),
            maxX: Math.max(result.maxX, bounds.maxX),
            minY: Math.min(result.minY, bounds.minY),
            maxY: Math.max(result.maxY, bounds.maxY)
          }
        : bounds;
    }
    return result;
  });
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

  function taskColor(tile: TaskTile): string | undefined {
    const x = colorSplits.x && tile.routes[colorSplits.x.id];
    const y = colorSplits.y && tile.routes[colorSplits.y.id];
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

  function goToPosition(point: Point) {
    if (!stage || !travelBounds) return;
    toastError(stage.moveTo(clampPosition(point)));
  }

  async function defineRegion(bounds: Bounds) {
    if (!instrument || !planAddHref) return;
    const url = new URL(planAddHref, page.url);
    for (const [key, value] of Object.entries(bounds)) url.searchParams.set(key, String(value));
    // The pathname is resolved above; only numeric bounds are appended here.
    // eslint-disable-next-line svelte/no-navigation-without-resolve
    await goto(`${planAddHref}${url.search}`, { keepFocus: true, noScroll: true });
    marquee = null;
  }

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
    <Crosshair width="14" height="14" />
    {label}
  </ContextMenu.Item>
{/snippet}

{#if instrument && stageBounds && stage}
  <StageCanvas
    bounds={stageBounds}
    orientation={stage.orientation}
    bind:viewport
    bind:marquee
    resolveDestination={(point, hits) => {
      menuGrid = positionLayer?.destination(point);
      menuTasks = (tasksLayer?.destinations(hits) ?? []).map((task) => ({ ...task, point: clampPosition(task.point) }));
      return menuGrid ?? (menuTasks.length === 1 ? menuTasks[0].point : clampPosition(point));
    }}
  >
    {#snippet overlay(view, width, cursor)}
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
    {#snippet menu(selection, canvasActions, center, fitBounds, previewDestination)}
      {#if 'bounds' in selection}
        <ContextMenu.Item onSelect={() => toastError(defineRegion(selection.bounds))}>
          <BoxSelect width="14" height="14" />
          {definingRegion ? 'Use as region' : 'Define region here'}
        </ContextMenu.Item>
        <ContextMenu.Separator />
      {:else if colorGroups.length}
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
        <ContextMenu.Separator />
      {/if}
      {#if 'point' in selection}
        {#if menuGrid}
          {@render movementAction('Go to grid cell', menuGrid, previewDestination)}
        {/if}
        {#if menuTasks.length === 1}
          {@render movementAction(`Go to Task ${menuTasks[0].order}`, menuTasks[0].point, previewDestination)}
        {:else if menuTasks.length > 1}
          <ContextMenu.Sub>
            <ContextMenu.SubTrigger><Crosshair width="14" height="14" />Go to task</ContextMenu.SubTrigger>
            <ContextMenu.SubContent sideOffset={8}>
              {#each menuTasks as task (task.order)}
                {@render movementAction(`Task ${task.order}`, task.point, previewDestination)}
              {/each}
            </ContextMenu.SubContent>
          </ContextMenu.Sub>
        {/if}
        {#if !menuGrid}
          {@render movementAction(
            menuTasks.length ? 'Go to clicked position' : 'Go to position',
            clampPosition(selection.point),
            previewDestination
          )}
        {/if}
      {/if}
      {@render canvasActions()}
      {#if 'point' in selection}
        {#if taskBounds}
          <ContextMenu.Item onSelect={() => fitBounds(taskBounds)}>
            <FitToScreen width="14" height="14" />
            Fit to tasks
          </ContextMenu.Item>
        {/if}
        {#if position && fov}
          <ContextMenu.Item onSelect={() => position && center(position)}>
            <CenterFocus width="14" height="14" />
            Recenter on live
          </ContextMenu.Item>
        {/if}
        {#if stage.anyMoving}
          <ContextMenu.Item variant="destructive" onSelect={() => toastError(stage.halt())}>
            <Stop width="14" height="14" />
            Halt
          </ContextMenu.Item>
        {/if}
      {/if}
    {/snippet}
    <RoutingRegions
      regions={routingRegions}
      bind:visible={() => routingRegionsVisible.get(), (value) => routingRegionsVisible.set(value)}
    />
    <Fov
      bind:this={fovLayer}
      {preview}
      bounds={liveBounds}
      bind:visible={() => prefs.stage.liveVisible.get(), (value) => prefs.stage.liveVisible.set(value)}
      onactivate={() => app.viewMode.set('fov')}
    />
    <Tasks
      bind:this={tasksLayer}
      tiles={instrument.taskTiles}
      fill={taskColor}
      selected={taskSelection.ids}
      bind:visible={() => tasksVisible.get(), (value) => tasksVisible.set(value)}
      color={themes.resolvedMode === 'light' ? '#52525b' : '#d4d4d8'}
      haloColor={themes.resolvedMode === 'light' ? '#ffffff' : '#18181b'}
      onselect={(ids, toggle) => {
        if (toggle) ids.forEach((id) => taskSelection.toggle(id));
        else {
          taskSelection.clear();
          taskSelection.add(...ids);
        }
      }}
      onactivate={(point) => fovLayer?.activateAt(point)}
    />
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
    <Position bind:this={positionLayer} {position} {fov} target={commandedTarget} constrain={clampPosition} />
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
