<script module lang="ts">
  export type StageViewport = { mode: 'auto' } | { mode: 'manual'; cx: number; cy: number; scale: number };
</script>

<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';

  import { CenterFocus, Close, Crosshair, FitToScreen, PanelRight, Stop } from '$lib/icons';
  import { Button, ContextMenu } from '$lib/kit';
  import { DEFAULT_STAGE_ORIENTATION, getVoxelApp } from '$lib/model';
  import { pref, toastError } from '$lib/utils';

  import { type Layer, type Painter, Surface } from './draw';
  import Inpaint from './features/Inpaint.svelte';
  import Live from './features/Live.svelte';
  import Snapshots from './features/Snapshots.svelte';
  import { getStageScene, type StageHit } from './scene.svelte';

  let { viewport = $bindable<StageViewport>({ mode: 'auto' }) }: { viewport?: StageViewport } = $props();

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
  const EDGE_PAD = 16; // px inset of the off-screen pose pointer from the viewport border

  let hostEl: HTMLDivElement;
  let surface: Surface | null = null;
  const collapsed = pref('stage:sidebar-collapsed', false);
  let boundsColor = '#3f3f46';
  let markerColor = '#22c55e';
  let marqueeColor = '#e5e7eb';
  // Camera scale + view width, mirrored from the (plain) camera each render to drive the reactive scale bar.
  let camScale = $state(0);
  let camViewW = $state(0);
  // Context menu: the hits contributing sections + the world point. 'marquee' mode acts on the selection
  // region (each layer's covered content); 'point' mode acts on the right-clicked spot.
  let menuHits = $state<StageHit[]>([]);
  let menuWorld: [number, number] = [0, 0];
  let menuMode = $state<'point' | 'marquee'>('point');
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

  function saveViewport() {
    if (!surface) return;
    const { cx, cy, scale } = surface.cam;
    viewport = { mode: 'manual', cx, cy, scale };
  }

  // Restore the parent-owned camera snapshot after the new surface has measured its viewport.
  function restoreViewport() {
    if (!surface || viewport.mode !== 'manual') return;
    surface.cam.orient = orient;
    surface.cam.cx = viewport.cx;
    surface.cam.cy = viewport.cy;
    surface.cam.scale = viewport.scale;
    reclamp();
  }

  // Keep the view within the stage frame without re-fitting (after the user has taken over).
  function reclamp() {
    if (!surface) return;
    if (stageBounds) surface.cam.clampPan(stageBounds);
    if (viewport.mode === 'manual') saveViewport();
    surface.invalidate();
  }

  // Wheel-zoom bounds: can't shrink past the stage fitting the viewport; zoom-in stops at the crispest
  // layer's native resolution, never past the hard MAX_SCALE ceiling.
  function scaleLimits(): readonly [number, number] {
    const layerMax = scene.maxScale();
    const max = layerMax != null ? Math.min(layerMax, MAX_SCALE) : MAX_SCALE;
    const b = stageBounds;
    if (!b || !surface) return [Number.EPSILON, max];
    const min =
      Math.min(surface.cam.viewW / (b.maxX - b.minX), surface.cam.viewH / (b.maxY - b.minY)) * BOUNDS_FIT_MARGIN;
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
    viewport = { mode: 'auto' };
    refit();
  }

  // Pan the view to center on the live stage position, keeping the current zoom (takes the view over).
  function recenterOnLive() {
    if (!surface || hereX == null || hereY == null) return;
    surface.cam.cx = hereX;
    surface.cam.cy = hereY;
    if (stageBounds) surface.cam.clampPan(stageBounds);
    saveViewport();
    surface.invalidate();
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
  // When that box is panned off-screen, a low-opacity chevron pinned to the viewport edge points back to it.
  const markerLayer: Layer = (p) => {
    const x = hereX;
    const y = hereY;
    if (x == null || y == null || !fov) return;
    const [fw, fh] = fov;
    p.strokeStyle = markerColor;
    p.lineWidthPx = 1.5;
    p.strokeRect(x - fw / 2, y - fh / 2, fw, fh);
    p.line(x - p.px(6), y, x + p.px(6), y);
    p.line(x, y - p.px(6), x, y + p.px(6));

    const b = p.viewBounds();
    if (x + fw / 2 > b.minX && x - fw / 2 < b.maxX && y + fh / 2 > b.minY && y - fh / 2 < b.maxY) return; // on-screen
    p.raw((ctx) => {
      const vw = ctx.canvas.width / devicePixelRatio;
      const vh = ctx.canvas.height / devicePixelRatio;
      const [sx, sy] = p.project(x, y);
      const px = Math.min(Math.max(sx, EDGE_PAD), vw - EDGE_PAD);
      const py = Math.min(Math.max(sy, EDGE_PAD), vh - EDGE_PAD);
      ctx.save();
      ctx.translate(px, py);
      ctx.rotate(Math.atan2(sy - vh / 2, sx - vw / 2));
      ctx.globalAlpha = 0.35;
      ctx.fillStyle = markerColor;
      ctx.beginPath();
      ctx.moveTo(7, 0);
      ctx.lineTo(-5, -6);
      ctx.lineTo(-5, 6);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    });
  };

  // Over-chrome: the persistent marquee selection as a dashed rect with a faint wash, drawn on top of all.
  const marqueeLayer: Layer = (p) => {
    const m = scene.marquee;
    if (!m) return;
    const w = m.maxX - m.minX;
    const h = m.maxY - m.minY;
    p.fillStyle = marqueeColor;
    p.globalAlpha = 0.08;
    p.fillRect(m.minX, m.minY, w, h);
    p.globalAlpha = 1;
    p.raw((ctx) => {
      const [x1, y1] = p.project(m.minX, m.maxY); // world max-Y is screen-top under the Y-up camera
      const [x2, y2] = p.project(m.maxX, m.minY);
      ctx.save();
      ctx.strokeStyle = marqueeColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.restore();
    });
  };

  // True when a world point falls inside the current marquee selection.
  function inMarquee(world: [number, number]): boolean {
    const m = scene.marquee;
    return !!m && world[0] >= m.minX && world[0] <= m.maxX && world[1] >= m.minY && world[1] <= m.maxY;
  }

  // Clear the marquee selection and redraw, if one is set.
  function clearMarquee() {
    if (!scene.marquee) return;
    scene.setMarquee(null);
    surface?.invalidate();
  }

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
      if (viewport.mode === 'auto') refit();
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
      surface.cam.fit(rq.bounds, rq.margin);
      if (stageBounds) surface.cam.clampPan(stageBounds);
      saveViewport(); // an explicit fit-to-region counts as taking the view over
      surface.invalidate();
    }
  );

  onMount(() => {
    boundsColor = getComputedStyle(hostEl).getPropertyValue('--color-border').trim() || boundsColor;
    markerColor = getComputedStyle(hostEl).getPropertyValue('--color-success').trim() || markerColor;
    marqueeColor = getComputedStyle(hostEl).getPropertyValue('--color-fg').trim() || marqueeColor;
    surface = new Surface(hostEl, {
      render: (p: Painter) => {
        boundsLayer(p);
        for (const layer of scene.layers) if (layer.visible) layer.draw(p);
        markerLayer(p);
        marqueeLayer(p);
        camScale = surface?.cam.scale ?? 0;
        camViewW = surface?.cam.viewW ?? 0;
      },
      onResize: () => (viewport.mode === 'manual' ? restoreViewport() : refit()),
      interactive: {
        constrain: (cam) => {
          if (stageBounds) cam.clampPan(stageBounds);
          saveViewport();
        },
        scaleLimits,
        onClick: (world, e) => {
          clearMarquee(); // a plain click drops the selection
          for (const { layer, hit } of scene.hits(world)) layer.onSelect?.(hit, e);
          surface?.invalidate();
        },
        onDblClick: (world) => {
          for (const { layer, hit } of scene.hits(world)) layer.onActivate?.(hit);
          surface?.invalidate();
        },
        onContextMenu: (world) => {
          menuWorld = world;
          const m = scene.marquee;
          if (m && inMarquee(world)) {
            menuMode = 'marquee';
            menuHits = scene.marqueeHits(m);
          } else {
            clearMarquee(); // right-clicking outside the selection drops it, then acts on the point
            menuMode = 'point';
            menuHits = scene.hits(world);
          }
        },
        marqueeOn: (e) => e.altKey, // Alt/Option-drag rubber-bands a selection region instead of panning
        onMarquee: (rect) => {
          scene.setMarquee(rect);
          surface?.invalidate();
        }
      }
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearMarquee();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      if (viewport.mode === 'manual') saveViewport();
      surface?.destroy();
    };
  });
</script>

<div class="flex h-full w-full">
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
          <div class="absolute top-3 right-3 z-10">
            <Button
              variant="ghost"
              size="icon-xs"
              title={collapsed.current ? 'Show panel' : 'Hide panel'}
              onclick={() => (collapsed.current = !collapsed.current)}
            >
              <PanelRight width="16" height="16" />
            </Button>
          </div>
          {#if cursor}
            <div
              class="canvas-overlay-halo pointer-events-none absolute bottom-4 left-4 z-10 flex gap-2 font-mono text-xs tabular-nums {cursorInBounds
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
            <div
              class="canvas-overlay-halo pointer-events-none absolute right-4 bottom-4 z-10 flex flex-col items-end gap-0.5"
            >
              <span class="font-mono text-xs text-fg-muted">{scaleBar.label}</span>
              <div class="h-1 rounded-full bg-fg-muted" style:width="{scaleBar.barPx}px"></div>
            </div>
          {/if}
        </div>
      {/snippet}
    </ContextMenu.Trigger>
    <ContextMenu.Content class="min-w-44">
      {#if menuMode === 'marquee'}
        {#each menuHits as mh (mh.layer.id)}
          {#if mh.layer.marqueeMenu}
            {@render mh.layer.marqueeMenu(mh.hit)}
            <ContextMenu.Separator />
          {/if}
        {/each}
        <ContextMenu.Item onSelect={clearMarquee}>
          <Close width="14" height="14" />
          Clear selection
        </ContextMenu.Item>
      {:else}
        <ContextMenu.Item onSelect={goToWorld}>
          <Crosshair width="14" height="14" />
          Go to position
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={fitToStage}>
          <FitToScreen width="14" height="14" />
          Fit to stage
        </ContextMenu.Item>
        {#if hereX != null && hereY != null && fov}
          <ContextMenu.Item onSelect={recenterOnLive}>
            <CenterFocus width="14" height="14" />
            Recenter on live
          </ContextMenu.Item>
        {/if}
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
      {/if}
    </ContextMenu.Content>
  </ContextMenu.Root>
  <div
    class="shrink-0 overflow-hidden bg-surface/80 transition-[width] duration-200 {collapsed.current
      ? 'w-0'
      : 'w-62 border-l border-border'}"
  >
    <div class="flex h-full w-full flex-col gap-4 overflow-y-auto py-1.5">
      <Live />
      <Inpaint />
      <Snapshots />
    </div>
  </div>
</div>

<style>
  .canvas-overlay-halo {
    filter: drop-shadow(0 1px 1px color-mix(in oklch, var(--color-canvas) 90%, transparent))
      drop-shadow(0 0 2px color-mix(in oklch, var(--color-canvas) 75%, transparent));
  }
</style>
