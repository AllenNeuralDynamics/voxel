<script lang="ts">
  import { Group } from 'svelte-konva';

  import { CenterFocus, Crosshair, Stop } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { getVoxelStation, NumericModel } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { formatSpatialDistance, formatSpatialValue } from '$lib/spatial-units';
  import { themes } from '$lib/themes/manager.svelte';
  import { displayName, pref, toastError } from '$lib/utils';

  import Fov from './Fov.svelte';
  import type { Point, Viewport } from './geometry';
  import Position from './Position.svelte';
  import Routing from './Routing.svelte';
  import StageCanvas from './StageCanvas.svelte';

  let { viewport = $bindable(null) }: { viewport?: Viewport | null } = $props();

  const app = getVoxelStation();
  let positionLayer = $state<Position>();
  const previews = getPreviewContext();
  const routingVisibility = pref<Record<string, boolean>>('stage:routing-visible', {});
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
  const routingColors = $derived(
    themes.resolvedMode === 'light'
      ? ['#0369a1', '#a16207', '#7e22ce', '#047857']
      : ['#7dd3fc', '#fcd34d', '#d8b4fe', '#6ee7b7']
  );
  const routingSplits = $derived(
    Array.from(instrument?.routingDimensions.values() ?? []).flatMap((dimension, index) =>
      dimension.axis && dimension.model instanceof NumericModel && Number.isFinite(dimension.model.value)
        ? [
            {
              model: dimension.model,
              threshold: dimension.model.value,
              axis: dimension.axis,
              id: dimension.id,
              label: displayName(dimension.id),
              lower: dimension.routeLabel('lower'),
              upper: dimension.routeLabel('upper'),
              color: routingColors[index % routingColors.length]
            }
          ]
        : []
    )
  );

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

  function scaleBar(scale: number, width: number) {
    const targetUm = (width * 0.2) / scale;
    const barUm = NICE_STEPS.findLast((step) => step <= targetUm) ?? NICE_STEPS[0];
    return { barPx: barUm * scale, label: barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm` };
  }
</script>

{#if instrument && stageBounds && stage}
  <StageCanvas
    bounds={stageBounds}
    orientation={stage.orientation}
    bind:viewport
    resolveDestination={(point) => positionLayer?.destination(point) ?? clampPosition(point)}
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
    {#snippet menu(selection, canvasActions, center)}
      {#if 'point' in selection}
        {@const target = selection.destination ?? selection.point}
        <ContextMenu.Item onSelect={() => goToPosition(target)}>
          <Crosshair width="14" height="14" />
          Go to position
        </ContextMenu.Item>
      {/if}
      {@render canvasActions()}
      {#if 'point' in selection}
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
    <Fov
      {preview}
      bounds={liveBounds}
      active={instrument.mode !== 'idle'}
      bind:visible={() => prefs.stage.liveVisible.get(), (value) => prefs.stage.liveVisible.set(value)}
      onactivate={() => app.viewMode.set('fov')}
    />
    <Group>
      {#each routingSplits as rule, index (rule.model)}
        {@const visibilityKey = `${instrument.stationId}/${instrument.id}/${rule.id}`}
        <Routing
          {rule}
          {index}
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
