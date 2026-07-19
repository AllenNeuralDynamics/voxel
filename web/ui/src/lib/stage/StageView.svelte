<script lang="ts">
  import { PersistedState, watch } from 'runed';
  import { onMount } from 'svelte';

  import { Crosshair, FitToScreen, PanelLeft, Stop } from '$lib/icons';
  import { Button, ContextMenu } from '$lib/kit';
  import { DEFAULT_STAGE_ORIENTATION, getVoxelApp } from '$lib/model';
  import { toastError } from '$lib/utils';

  import { type Layer, type Painter, Surface } from './draw';
  import Snapshots from './features/Snapshots.svelte';
  import { getStageScene, type StageHit } from './scene.svelte';

  const app = getVoxelApp();
  const scene = getStageScene();
  const stage = $derived(app.instrument?.stage ?? null);

  // Field of view (µm) and per-axis orientation come from the active instrument's stage.
  const fov = $derived(stage?.fov ?? null);
  const orient = $derived(stage?.orientation ?? DEFAULT_STAGE_ORIENTATION);

  // Live stage position (µm) drives the "you are here" FOV marker.
  const hereX = $derived(stage?.x?.position?.value ?? null);
  const hereY = $derived(stage?.y?.position?.value ?? null);

  // Imageable stage extent (soft limits + half a FOV); null until the limits are known.
  const stageBounds = $derived(stage?.bounds(true) ?? null);

  const BOUNDS_FIT_MARGIN = 0.9; // matches Camera.fit's default, so minScale equals the fit-to-bounds scale
  const MAX_SCALE = 7; // hard px-per-µm zoom-in ceiling; layers may ask for less (e.g. native tile resolution)
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
  const shadow = 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]'; // legibility over the canvas

  let hostEl: HTMLDivElement;
  let surface: Surface | null = null;
  const collapsed = new PersistedState('voxel-stage-sidebar-collapsed', false);
  let boundsColor = '#3f3f46';
  let markerColor = '#22c55e';
  let userAdjusted = false; // once the user pans/zooms, stop auto-fitting on resize
  // Camera scale + view width, mirrored from the (plain) camera each render to drive the reactive scale bar.
  let camScale = $state(0);
  let camViewW = $state(0);
  // Context menu: the hits at the right-clicked point (each layer contributes a section) + the world point.
  let menuHits = $state<StageHit[]>([]);
  let menuWorld: [number, number] = [0, 0];
  // Live cursor position in stage µm for the readout overlay; null when the pointer is off the canvas.
  let cursor = $state<[number, number] | null>(null);
  // Whether the cursor is within the reachable stage limits (unknown limits count as in-range).
  const cursorInBounds = $derived.by(() => {
    const b = stage?.bounds(false);
    if (!cursor || !b) return true;
    const [x, y] = cursor;
    return x >= b.minX && x <= b.maxX && y >= b.minY && y <= b.maxY;
  });

  // Sync orientation and re-fit the camera to the stage frame, then request a redraw.
  function refit() {
    if (!surface) return;
    surface.cam.orient = orient;
    if (stageBounds) surface.cam.fit(stageBounds);
    surface.invalidate();
  }

  // Keep the view within the stage frame without re-fitting (after the user has taken over).
  function reclamp() {
    if (!surface || !stageBounds) return;
    surface.cam.clampPan(stageBounds);
    surface.invalidate();
  }

  // Wheel-zoom bounds: can't shrink past the stage fitting the viewport; zoom-in stops at the crispest
  // layer's native resolution, never past the hard MAX_SCALE ceiling.
  function scaleLimits(): readonly [number, number] {
    const layerMax = scene.maxScale();
    const max = layerMax != null ? Math.min(layerMax, MAX_SCALE) : MAX_SCALE;
    const b = stageBounds;
    if (!b || !surface) return [Number.EPSILON, max];
    const min = Math.min(surface.cam.viewW / (b.maxX - b.minX), surface.cam.viewH / (b.maxY - b.minY)) * BOUNDS_FIT_MARGIN;
    return [min, max];
  }

  // Clamp a world point to the reachable stage position (soft limits, no FOV inset).
  function clampToStage(wx: number, wy: number): [number, number] {
    const b = stage?.bounds(false);
    if (!b) return [wx, wy];
    return [Math.min(Math.max(wx, b.minX), b.maxX), Math.min(Math.max(wy, b.minY), b.maxY)];
  }

  // Move the stage to the right-clicked position (z unchanged), clamped to the reachable soft limits.
  function goToWorld() {
    if (!stage) return;
    const [x, y] = clampToStage(...menuWorld);
    toastError(stage.moveTo({ x, y }));
  }

  // Reset the view: re-fit to the stage frame and resume auto-fitting.
  function fitToStage() {
    userAdjusted = false;
    refit();
  }

  function halt() {
    if (stage) toastError(stage.halt());
  }

  function trackCursor(e: PointerEvent) {
    if (!surface) return;
    const rect = hostEl.getBoundingClientRect();
    cursor = surface.cam.unproject(e.clientX - rect.left, e.clientY - rect.top);
  }

  // Baked chrome: the imageable stage extent as a frame, drawn under all content.
  const boundsLayer: Layer = (p) => {
    const b = stageBounds;
    if (!b) return;
    p.strokeStyle = boundsColor;
    p.lineWidthPx = 1;
    p.strokeRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);
  };

  // Over-chrome: the live stage position + FOV as a "you are here" box with a crosshair, drawn over content.
  const markerLayer: Layer = (p) => {
    if (hereX == null || hereY == null || !fov) return;
    const [fw, fh] = fov;
    p.strokeStyle = markerColor;
    p.lineWidthPx = 1.5;
    p.strokeRect(hereX - fw / 2, hereY - fh / 2, fw, fh);
    p.line(hereX - p.px(6), hereY, hereX + p.px(6), hereY);
    p.line(hereX, hereY - p.px(6), hereX, hereY + p.px(6));
  };

  // Scale bar: a "nice" round length filling ~20% of the canvas width, from the mirrored camera scale.
  const scaleBar = $derived.by(() => {
    if (camScale <= 0 || camViewW <= 0) return null;
    const targetUm = (camViewW * 0.2) / camScale;
    const barUm = NICE_STEPS.findLast((s) => s <= targetUm) ?? NICE_STEPS[0];
    return { barPx: barUm * camScale, label: barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm` };
  });

  // Re-fit whenever the stage frame or its orientation resolves/changes — unless the user has taken over.
  watch(
    () => [stageBounds, orient] as const,
    () => {
      if (!userAdjusted) refit();
    }
  );

  // Redraw as the live stage position moves, and when registered layers change (structure or content).
  watch(
    () => [hereX, hereY, scene.layers, scene.generation] as const,
    () => surface?.invalidate()
  );

  // Honor a feature's request to frame a region (e.g. "fit selected snapshots").
  watch(
    () => scene.viewRequest,
    (rq) => {
      if (!rq || !surface) return;
      userAdjusted = true; // an explicit fit-to-region counts as taking the view over
      surface.cam.fit(rq.bounds, rq.margin);
      if (stageBounds) surface.cam.clampPan(stageBounds);
      surface.invalidate();
    }
  );

  onMount(() => {
    boundsColor = getComputedStyle(hostEl).getPropertyValue('--color-border').trim() || boundsColor;
    markerColor = getComputedStyle(hostEl).getPropertyValue('--color-success').trim() || markerColor;
    surface = new Surface(hostEl, {
      render: (p: Painter) => {
        boundsLayer(p);
        for (const layer of scene.layers) if (layer.visible) layer.draw(p);
        markerLayer(p);
        camScale = surface?.cam.scale ?? 0;
        camViewW = surface?.cam.viewW ?? 0;
      },
      onResize: () => (userAdjusted ? reclamp() : refit()),
      interactive: {
        constrain: (cam) => {
          userAdjusted = true;
          if (stageBounds) cam.clampPan(stageBounds);
        },
        scaleLimits,
        onClick: (world, e) => {
          for (const { layer, hit } of scene.hits(world)) layer.onSelect?.(hit, e);
          surface?.invalidate();
        },
        onDblClick: (world) => {
          for (const { layer, hit } of scene.hits(world)) layer.onActivate?.(hit);
          surface?.invalidate();
        },
        onContextMenu: (world) => {
          menuWorld = world;
          menuHits = scene.hits(world);
        }
      }
    });
    return () => surface?.destroy();
  });
</script>

<div class="flex h-full w-full">
  <div
    class="shrink-0 overflow-hidden bg-surface/30 transition-[width] duration-200 {collapsed.current
      ? 'w-0'
      : 'w-60 border-r border-border'}"
  >
    <div class="flex h-full w-60 flex-col gap-3 overflow-y-auto py-2">
      <Snapshots />
    </div>
  </div>
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      {#snippet child({ props })}
        <div
          bind:this={hostEl}
          {...props}
          class="relative h-full min-w-0 flex-1 overflow-hidden bg-canvas"
          onpointermove={trackCursor}
          onpointerleave={() => (cursor = null)}
        >
          <div class="absolute top-3 left-3 z-10">
            <Button
              variant="ghost"
              size="icon-xs"
              title={collapsed.current ? 'Show panel' : 'Hide panel'}
              onclick={() => (collapsed.current = !collapsed.current)}
            >
              <PanelLeft width="16" height="16" />
            </Button>
          </div>
          {#if cursor}
          <div
            class="pointer-events-none absolute bottom-4 left-4 z-10 flex gap-2 font-mono text-xs tabular-nums {shadow} {cursorInBounds
              ? 'text-fg-muted'
              : 'text-fg-faint'}"
          >
            <span>X {Math.round(cursor[0])}</span>
            <span>Y {Math.round(cursor[1])} µm</span>
            {#if !cursorInBounds}
              <span>· out of range</span>
            {/if}
          </div>
        {/if}
        {#if scaleBar}
          <div class="pointer-events-none absolute right-4 bottom-4 z-10 flex flex-col items-end gap-0.5">
            <span class="font-mono text-xs text-fg-muted {shadow}">{scaleBar.label}</span>
            <div class="h-1 rounded-full bg-fg-muted {shadow}" style:width="{scaleBar.barPx}px"></div>
          </div>
        {/if}
      </div>
    {/snippet}
  </ContextMenu.Trigger>
  <ContextMenu.Content class="min-w-44">
    <ContextMenu.Item onSelect={goToWorld}>
      <Crosshair width="14" height="14" />
      Go to position
    </ContextMenu.Item>
    <ContextMenu.Item onSelect={fitToStage}>
      <FitToScreen width="14" height="14" />
      Fit to stage
    </ContextMenu.Item>
    {#if stage?.anyMoving}
      <ContextMenu.Item variant="destructive" onSelect={halt}>
        <Stop width="14" height="14" />
        Halt
      </ContextMenu.Item>
    {/if}
    {#each menuHits as mh (mh.layer.id)}
      <ContextMenu.Separator />
      {#if mh.layer.menu}{@render mh.layer.menu(mh.hit)}{/if}
    {/each}
    </ContextMenu.Content>
  </ContextMenu.Root>
</div>
