<script lang="ts">
  import { Popover } from 'bits-ui';
  import { ElementSize } from 'runed';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  import { ChevronLeft, Crosshair, GridLines, TrashCanOutline } from '$lib/icons';
  import { Button } from '$lib/kit';
  import { channelBoundingBox, getVoxelApp, type Preview, wheelZoomFactor } from '$lib/model';
  import { clampTopLeft, toastError } from '$lib/utils';

  import PreviewCanvas from './PreviewCanvas.svelte';
  import PreviewControls from './PreviewControls.svelte';
  import PreviewNavigator from './PreviewNavigator.svelte';
  import SnapshotFlyOverlay from './SnapshotFlyOverlay.svelte';
  import SnapshotInfo from './SnapshotInfo.svelte';

  interface Props {
    previewer: Preview;
    /** Field of view as a `[width, height]` µm tuple (`instrument.fov`), or null when unavailable. */
    fov: [number, number] | null;
  }

  let { previewer, fov }: Props = $props();

  const app = getVoxelApp();
  const snaps = app.snaps;
  const instrument = $derived(app.instrument);
  const previewing = $derived(app.instrument?.mode === 'preview');

  const ALIGN_EDGES = [
    { edge: 'top', label: 'Top' },
    { edge: 'bottom', label: 'Bottom' },
    { edge: 'left', label: 'Left' },
    { edge: 'right', label: 'Right' },
    { edge: 'center', label: 'Center' }
  ] as const;

  // Overlay chrome layered onto a ghost icon Button so it reads over the image.
  const overlayBtn = 'rounded-full border-border/50 bg-floating/90 text-fg-muted shadow-lg backdrop-blur-sm';

  let viewEl: HTMLDivElement;
  const containerSize = new ElementSize(() => viewEl);

  // Snapshot image object URL — recreated when the active snap changes, revoked on change/unmount.
  let snapUrl = $state<string | null>(null);
  $effect(() => {
    const active = snaps.active;
    if (!active) {
      snapUrl = null;
      return;
    }
    const url = URL.createObjectURL(active.blob);
    snapUrl = url;
    return () => URL.revokeObjectURL(url);
  });

  /** Multiplicative, anchored zoom against the live view aspect. Shared with the navigator via prop. */
  function zoomBy(factor: number, anchorX: number, anchorY: number, anchorFracX = 0.5, anchorFracY = 0.5) {
    if (!viewEl) return;
    const rect = viewEl.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const canvasAspect = rect.width / rect.height;
    const bb = previewer.boundingBoxAspect;
    const vp = previewer.viewport;
    let w: number, h: number;
    if (canvasAspect >= bb) {
      h = Math.max(0.01, Math.min(1, vp.h * factor));
      w = Math.max(0.01, Math.min(1, (h * canvasAspect) / bb));
    } else {
      w = Math.max(0.01, Math.min(1, vp.w * factor));
      h = Math.max(0.01, Math.min(1, (w * bb) / canvasAspect));
    }
    previewer.setViewport({
      x: clampTopLeft(anchorX - anchorFracX * w, w),
      y: clampTopLeft(anchorY - anchorFracY * h, h),
      w,
      h
    });
    previewer.queueViewportUpdate({ ...previewer.viewport });
  }

  // Pan/zoom acts on the live view only; while a snap is shown the body is a static image.
  function setupPanZoom(el: HTMLElement): () => void {
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let startViewport = { ...previewer.viewport };
    let wheelIdleTimer: number | null = null;
    const WHEEL_IDLE_DELAY_MS = 250;

    const scheduleWheelIdleReset = () => {
      if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
      wheelIdleTimer = window.setTimeout(() => {
        previewer.isPanZoomActive = false;
        wheelIdleTimer = null;
      }, WHEEL_IDLE_DELAY_MS);
    };

    const pointerDown = (e: PointerEvent) => {
      if (snaps.active || e.button !== 0) return;
      el.setPointerCapture(e.pointerId);
      isPanning = true;
      panStartX = e.clientX;
      panStartY = e.clientY;
      startViewport = { ...previewer.viewport };
      previewer.isPanZoomActive = true;
    };

    const pointerMove = (e: PointerEvent) => {
      if (!isPanning) return;
      const rect = el.getBoundingClientRect();
      const dx = ((e.clientX - panStartX) / rect.width) * previewer.viewport.w;
      const dy = ((e.clientY - panStartY) / rect.height) * previewer.viewport.h;
      const newX = clampTopLeft(startViewport.x - dx, previewer.viewport.w);
      const newY = clampTopLeft(startViewport.y - dy, previewer.viewport.h);
      previewer.setViewport({ x: newX, y: newY, w: previewer.viewport.w, h: previewer.viewport.h });
      previewer.queueViewportUpdate({ ...previewer.viewport });
    };

    const pointerUp = (e: PointerEvent) => {
      if (e.button !== 0) return;
      el.releasePointerCapture(e.pointerId);
      isPanning = false;
      previewer.isPanZoomActive = false;
      previewer.queueViewportUpdate({ ...previewer.viewport });
    };

    const wheel = (e: WheelEvent) => {
      if (snaps.active) return;
      e.preventDefault();
      previewer.isPanZoomActive = true;
      const rect = el.getBoundingClientRect();
      const vp = previewer.viewport;
      // Keep the sensor point under the cursor fixed on screen.
      const mouseX = (e.clientX - rect.left) / rect.width;
      const mouseY = (e.clientY - rect.top) / rect.height;
      zoomBy(wheelZoomFactor(e), vp.x + mouseX * vp.w, vp.y + mouseY * vp.h, mouseX, mouseY);
      scheduleWheelIdleReset();
    };

    el.addEventListener('pointerdown', pointerDown, { passive: true });
    el.addEventListener('pointermove', pointerMove, { passive: true });
    el.addEventListener('pointerup', pointerUp, { passive: true });
    el.addEventListener('wheel', wheel, { passive: false });

    return () => {
      el.removeEventListener('pointerdown', pointerDown);
      el.removeEventListener('pointermove', pointerMove);
      el.removeEventListener('pointerup', pointerUp);
      el.removeEventListener('wheel', wheel);
      if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
    };
  }

  onMount(() => setupPanZoom(viewEl));

  // ── Scale bar ──────────────────────────────────────────────────────
  // Pick a "nice" round bar length that fits ~15-25% of the canvas width.
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

  const scaleBar = $derived.by(() => {
    const { maxW, maxH } = channelBoundingBox(previewer.channels);
    const [fovW, fovH] = fov ?? [0, 0];
    if (maxW <= 0 || maxH <= 0 || fovW <= 0 || fovH <= 0) return null;

    const cw = containerSize.width;
    const ch = containerSize.height;
    if (cw <= 0 || ch <= 0) return null;

    const vp = previewer.viewport;
    const vpAspect = (vp.w * maxW) / (vp.h * maxH);
    const canvasAspect = cw / ch;
    const drawW = canvasAspect > vpAspect ? ch * vpAspect : cw;

    const umPerPx = (vp.w * fovW) / drawW;
    if (!Number.isFinite(umPerPx) || umPerPx <= 0) return null;

    const targetUm = umPerPx * cw * 0.2;
    const barUm = NICE_STEPS.findLast((s) => s <= targetUm) ?? NICE_STEPS[0];
    const barPx = barUm / umPerPx;

    const label = barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm`;
    return { barPx, label };
  });

  // Navigator is a live-preview locator: shown while preview is running and either a snap is up or we're zoomed in.
  const zoomed = $derived(previewer.viewport.w < 1 || previewer.viewport.h < 1);
  const showNavigator = $derived(previewing && (snaps.active !== null || zoomed));
</script>

<div class="flex h-full flex-col bg-canvas">
  <div class="relative flex-1 overflow-hidden" data-fly-origin>
    <!-- Source (also the pan/zoom target). Branches stack so they cross-fade on switch. -->
    <div class="absolute inset-0" bind:this={viewEl}>
      {#if snaps.active && snapUrl}
        <div class="absolute inset-0 flex items-center justify-center" transition:fade={{ duration: 120 }}>
          <img src={snapUrl} alt={snaps.active.label} class="max-h-full max-w-full object-contain" />
        </div>
      {:else}
        <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
          <PreviewCanvas {previewer} />
        </div>
      {/if}
    </div>

    <!-- Overlays -->
    <div class="pointer-events-none absolute right-4 bottom-4 left-4 flex items-end justify-between">
      {#if snaps.active}
        {@const active = snaps.active}
        <div transition:fade={{ duration: 150 }}>
          <SnapshotInfo snap={active} {previewer} onRename={(label) => snaps.rename(active.id, label)} />
        </div>
      {:else}
        <div transition:fade={{ duration: 150 }}>
          <PreviewControls {previewer} />
        </div>
      {/if}
      <div class="flex flex-col items-end gap-1.5">
        {#if showNavigator}
          <div transition:fade={{ duration: 150 }}>
            <PreviewNavigator {previewer} {zoomBy} />
          </div>
        {/if}
        {#if !snaps.active && scaleBar}
          <div class="flex flex-col items-end gap-0.5" transition:fade={{ duration: 150 }}>
            <span class="font-mono text-xs text-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">{scaleBar.label}</span>
            <div
              class="h-1 rounded-full bg-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
              style:width="{scaleBar.barPx}px"
            ></div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Back to live (snap only) -->
    {#if snaps.active}
      <button
        type="button"
        transition:fade={{ duration: 150 }}
        class="pointer-events-auto absolute top-4 left-4 flex items-center gap-1 rounded-full border border-border/50 bg-floating/90 py-1 pr-3 pl-2 text-sm text-fg shadow-lg backdrop-blur-sm transition-colors hover:bg-element-hover"
        onclick={() => snaps.view(null)}
      >
        <ChevronLeft width="16" height="16" />
        Live
      </button>
    {/if}

    {#if snaps.active}
      {@const active = snaps.active}
      <div class="pointer-events-auto absolute top-4 right-4 flex items-center gap-1" transition:fade={{ duration: 150 }}>
        <Button
          variant="ghost"
          size="icon"
          title="Go to position"
          class={overlayBtn}
          onclick={() => toastError(instrument?.moveStage({ x: active.stageX, y: active.stageY, z: active.stageZ }))}
        >
          <Crosshair width="15" height="15" />
        </Button>
        <Popover.Root>
          <Popover.Trigger>
            {#snippet child({ props })}
              <Button
                {...props}
                variant="ghost"
                size="icon"
                disabled={!instrument?.activeProfile}
                title="Align grid to snapshot"
                class={overlayBtn}
              >
                <GridLines width="15" height="15" />
              </Button>
            {/snippet}
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              side="bottom"
              align="end"
              sideOffset={6}
              class="z-50 flex w-32 flex-col rounded-md border border-border bg-surface p-1 text-sm shadow-lg outline-none"
            >
              {#each ALIGN_EDGES as { edge, label } (edge)}
                <button
                  class="rounded px-2 py-1 text-left transition-colors hover:bg-floating"
                  onclick={() => toastError(instrument?.alignStencil(edge, { x: active.stageX, y: active.stageY }))}
                >
                  {label}
                </button>
              {/each}
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
        <Button
          variant="ghost"
          size="icon"
          title="Delete snapshot"
          class="{overlayBtn} hover:text-danger"
          onclick={() => snaps.remove(active.id)}
        >
          <TrashCanOutline width="15" height="15" />
        </Button>
      </div>
    {/if}
  </div>

  <SnapshotFlyOverlay />
</div>
