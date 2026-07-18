<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';

  import { Crosshair, FitToScreen, Stop } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { DEFAULT_STAGE_ORIENTATION, getVoxelApp } from '$lib/model';
  import { toastError } from '$lib/utils';

  import { type Layer, type Painter, Surface } from './draw';
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
  const MAX_SCALE = 100; // CSS px per µm zoom-in ceiling (no tiles yet, so just a sane cap)
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];
  const shadow = 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]'; // legibility over the canvas

  let hostEl: HTMLDivElement;
  let surface: Surface | null = null;
  let boundsColor = '#3f3f46';
  let markerColor = '#22c55e';
  let userAdjusted = false; // once the user pans/zooms, stop auto-fitting on resize
  // Camera scale + view width, mirrored from the (plain) camera each render to drive the reactive scale bar.
  let camScale = $state(0);
  let camViewW = $state(0);
  // Context menu: the hits at the right-clicked point (each layer contributes a section) + the world point.
  let menuHits = $state<StageHit[]>([]);
  let menuWorld: [number, number] = [0, 0];

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

  // Wheel-zoom bounds: can't shrink past the stage fitting the viewport; a sane ceiling for zoom-in.
  function scaleLimits(): readonly [number, number] {
    const b = stageBounds;
    if (!b || !surface) return [Number.EPSILON, MAX_SCALE];
    const min = Math.min(surface.cam.viewW / (b.maxX - b.minX), surface.cam.viewH / (b.maxY - b.minY)) * BOUNDS_FIT_MARGIN;
    return [min, MAX_SCALE];
  }

  // Move the stage to the right-clicked position (z unchanged), clamped to the reachable soft limits.
  function goToWorld() {
    if (!stage) return;
    const b = stage.bounds(false);
    const [wx, wy] = menuWorld;
    const x = b ? Math.min(Math.max(wx, b.minX), b.maxX) : wx;
    const y = b ? Math.min(Math.max(wy, b.minY), b.maxY) : wy;
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
        onClick: (world) => {
          for (const { layer, hit } of scene.hits(world)) layer.onSelect?.(hit);
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

<ContextMenu.Root>
  <ContextMenu.Trigger>
    {#snippet child({ props })}
      <div bind:this={hostEl} {...props} class="relative h-full w-full overflow-hidden bg-canvas">
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
