<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';

  import { channelBoundingBox, compositeViewFrames, type Preview, wheelZoomFactor } from '$lib/model';
  import { clampTopLeft } from '$lib/utils';

  import PreviewControls from './PreviewControls.svelte';
  import PreviewNavigator from './PreviewNavigator.svelte';

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;

  interface Props {
    previewer: Preview;
    /** Field of view as a `[width, height]` µm tuple (`instrument.fov`), or null when unavailable. */
    fov: [number, number] | null;
  }

  let { previewer, fov }: Props = $props();

  let ctx: CanvasRenderingContext2D | null = null;
  let isRendering = false;
  let needsRedraw = false;
  let animFrameId: number | null = null;

  let canvasContainerEl: HTMLDivElement;

  // Track canvas container size reactively (the middle grid cell, not the whole component)
  const containerSize = new ElementSize(() => canvasContainerEl);

  // Watch for redraw signals from PreviewManager
  watch(
    () => previewer.redrawGeneration,
    () => {
      needsRedraw = true;
    }
  );

  // Resize canvas pixel dimensions to match container at device pixel ratio
  watch(
    () => [containerSize.width, containerSize.height] as const,
    ([w, h]) => {
      if (!canvasEl || w <= 0 || h <= 0) return;
      const dpr = devicePixelRatio;
      const newW = Math.round(w * dpr);
      const newH = Math.round(h * dpr);
      if (canvasEl.width !== newW || canvasEl.height !== newH) {
        canvasEl.width = newW;
        canvasEl.height = newH;
        needsRedraw = true;
      }
    }
  );

  function frameLoop() {
    if (!isRendering) return;

    if (needsRedraw && ctx && canvasEl) {
      needsRedraw = false;
      compositeViewFrames(ctx, canvasEl, previewer.channels, previewer.viewport);
    }

    animFrameId = requestAnimationFrame(frameLoop);
  }

  /** Multiplicative, anchored zoom against the live canvas aspect. Shared with the navigator via prop. */
  function zoomBy(factor: number, anchorX: number, anchorY: number, anchorFracX = 0.5, anchorFracY = 0.5) {
    if (!canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
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
    previewer.setViewport({ x: clampTopLeft(anchorX - anchorFracX * w, w), y: clampTopLeft(anchorY - anchorFracY * h, h), w, h });
    previewer.queueViewportUpdate({ ...previewer.viewport });
  }

  function setupPanZoom(canvas: HTMLCanvasElement): () => void {
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
      if (e.button !== 0) return;
      canvas.setPointerCapture(e.pointerId);
      isPanning = true;
      panStartX = e.clientX;
      panStartY = e.clientY;
      startViewport = { ...previewer.viewport };
      previewer.isPanZoomActive = true;
    };

    const pointerMove = (e: PointerEvent) => {
      if (!isPanning) return;
      const rect = canvas.getBoundingClientRect();
      const dx = ((e.clientX - panStartX) / rect.width) * previewer.viewport.w;
      const dy = ((e.clientY - panStartY) / rect.height) * previewer.viewport.h;
      const newX = clampTopLeft(startViewport.x - dx, previewer.viewport.w);
      const newY = clampTopLeft(startViewport.y - dy, previewer.viewport.h);
      previewer.setViewport({ x: newX, y: newY, w: previewer.viewport.w, h: previewer.viewport.h });
      previewer.queueViewportUpdate({ ...previewer.viewport });
    };

    const pointerUp = (e: PointerEvent) => {
      if (e.button !== 0) return;
      canvas.releasePointerCapture(e.pointerId);
      isPanning = false;
      previewer.isPanZoomActive = false;
      previewer.queueViewportUpdate({ ...previewer.viewport });
    };

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      previewer.isPanZoomActive = true;
      const rect = canvas.getBoundingClientRect();
      const vp = previewer.viewport;
      // Keep the sensor point under the cursor fixed on screen.
      const mouseX = (e.clientX - rect.left) / rect.width;
      const mouseY = (e.clientY - rect.top) / rect.height;
      zoomBy(wheelZoomFactor(e), vp.x + mouseX * vp.w, vp.y + mouseY * vp.h, mouseX, mouseY);
      scheduleWheelIdleReset();
    };

    canvas.addEventListener('pointerdown', pointerDown, { passive: true });
    canvas.addEventListener('pointermove', pointerMove, { passive: true });
    canvas.addEventListener('pointerup', pointerUp, { passive: true });
    canvas.addEventListener('wheel', wheel, { passive: false });

    return () => {
      canvas.removeEventListener('pointerdown', pointerDown);
      canvas.removeEventListener('pointermove', pointerMove);
      canvas.removeEventListener('pointerup', pointerUp);
      canvas.removeEventListener('wheel', wheel);
      if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
    };
  }

  onMount(() => {
    // Seed canvas size immediately from container layout (before ResizeObserver fires)
    const dpr = devicePixelRatio;
    const initW = canvasContainerEl.clientWidth;
    const initH = canvasContainerEl.clientHeight;
    if (initW > 0 && initH > 0) {
      canvasEl.width = Math.round(initW * dpr);
      canvasEl.height = Math.round(initH * dpr);
    }

    ctx = canvasEl.getContext('2d');

    isRendering = true;
    frameLoop();

    const cleanupPanZoom = setupPanZoom(canvasEl);

    return () => {
      isRendering = false;
      if (animFrameId !== null) cancelAnimationFrame(animFrameId);
      cleanupPanZoom();
    };
  });

  // ── Scale bar ──────────────────────────────────────────────────────
  // Pick a "nice" round bar length that fits ~15-25% of the canvas width.

  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

  let scaleBar = $derived.by(() => {
    const { maxW, maxH } = channelBoundingBox(previewer.channels);
    const [fovW, fovH] = fov ?? [0, 0];
    if (maxW <= 0 || maxH <= 0 || fovW <= 0 || fovH <= 0) return null;

    const cw = containerSize.width;
    const ch = containerSize.height;
    if (cw <= 0 || ch <= 0) return null;

    // Compute draw area (same contain-fit as compositeViewFrames)
    const vp = previewer.viewport;
    const vpAspect = (vp.w * maxW) / (vp.h * maxH);
    const canvasAspect = cw / ch;
    const drawW = canvasAspect > vpAspect ? ch * vpAspect : cw;

    // µm per CSS pixel
    const umPerPx = (vp.w * fovW) / drawW;
    if (!Number.isFinite(umPerPx) || umPerPx <= 0) return null;

    // Target bar: ~20% of canvas width
    const targetUm = umPerPx * cw * 0.2;
    const barUm = NICE_STEPS.findLast((s) => s <= targetUm) ?? NICE_STEPS[0];
    const barPx = barUm / umPerPx;

    const label = barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm`;
    return { barPx, label };
  });

  // The navigator (with its viewport controls) shows only while zoomed in — a box covering the whole
  // frame is redundant. Later: also show while viewing a snapshot with preview running.
  const showNavigator = $derived(previewer.viewport.w < 1 || previewer.viewport.h < 1);
</script>

<div class="flex h-full flex-col bg-canvas" bind:this={containerEl}>
  <!-- Center: Canvas -->
  <div class="relative flex flex-1 items-center justify-center overflow-hidden" bind:this={canvasContainerEl}>
    <canvas bind:this={canvasEl} class="h-full w-full"></canvas>
    <!-- Overlay: histograms (bottom-left) + viewport navigator over scale bar (bottom-right) -->
    <div class="pointer-events-none absolute right-4 bottom-4 left-4 flex items-end justify-between">
      <PreviewControls {previewer} />
      <div class="flex flex-col items-end gap-1.5">
        {#if showNavigator}
          <PreviewNavigator {previewer} {zoomBy} />
        {/if}
        {#if scaleBar}
          <div class="flex flex-col items-end gap-0.5">
            <span class="font-mono text-xs text-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">{scaleBar.label}</span
            >
            <div
              class="h-1 rounded-full bg-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
              style:width="{scaleBar.barPx}px"
            ></div>
          </div>
        {/if}
      </div>
    </div>
  </div>
</div>
