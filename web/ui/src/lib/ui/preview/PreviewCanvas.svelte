<script lang="ts">
  import { onMount } from 'svelte';
  import { watch, ElementSize } from 'runed';
  import { Bargraph } from '$lib/icons';
  import PreviewInfo from './PreviewInfo.svelte';
  import PanZoomControls from './PanZoomControls.svelte';
  import Histogram from './Histogram.svelte';
  import type { PreviewState } from '$lib/main';
  import { channelBoundingBox, compositeTiledFrames } from '$lib/main/preview.svelte.ts';
  import { clampTopLeft } from '$lib/utils';

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;

  interface Props {
    previewer: PreviewState;
    fov: { width: number; height: number };
  }

  let { previewer, fov }: Props = $props();

  let ctx: CanvasRenderingContext2D | null = null;
  let isRendering = false;
  let needsRedraw = false;
  let animFrameId: number | null = null;
  let showHistograms = $state(true);

  let canvasContainerEl: HTMLDivElement;

  // Track canvas container size reactively (the middle grid cell, not the whole component)
  const containerSize = new ElementSize(() => canvasContainerEl);

  // Watch for redraw signals from PreviewState
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
      compositeTiledFrames(ctx, canvasEl, previewer.channels, previewer.viewport);
    }

    animFrameId = requestAnimationFrame(frameLoop);
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
      const rect = canvas.getBoundingClientRect();
      previewer.isPanZoomActive = true;

      const zoomSensitivity = 0.001;
      const delta = -e.deltaY * zoomSensitivity;
      const vp = previewer.viewport;

      // Derive w from h (or vice versa) to fill the canvas as you zoom in.
      // At full zoom-out (w=h=1) contain-fit may show bars; zooming in
      // increases w/h ratio until the image fills the canvas, then both
      // shrink together maintaining the fill.
      const bbAspect = previewer.boundingBoxAspect;
      const canvasAspect = rect.width / rect.height;
      let newW: number, newH: number;
      if (canvasAspect >= bbAspect) {
        newH = Math.max(0.01, Math.min(1.0, vp.h - delta));
        newW = Math.max(0.01, Math.min(1.0, (newH * canvasAspect) / bbAspect));
      } else {
        newW = Math.max(0.01, Math.min(1.0, vp.w - delta));
        newH = Math.max(0.01, Math.min(1.0, (newW * bbAspect) / canvasAspect));
      }

      // Point on sensor under cursor
      const mouseX = (e.clientX - rect.left) / rect.width;
      const mouseY = (e.clientY - rect.top) / rect.height;
      const sensorX = vp.x + mouseX * vp.w;
      const sensorY = vp.y + mouseY * vp.h;

      // Recompute top-left so sensorX/Y stays under cursor
      let newX = sensorX - mouseX * newW;
      let newY = sensorY - mouseY * newH;
      newX = clampTopLeft(newX, newW);
      newY = clampTopLeft(newY, newH);

      previewer.setViewport({ x: newX, y: newY, w: newW, h: newH });
      previewer.queueViewportUpdate({ ...previewer.viewport });
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

  // Channels with names (for histogram strip)
  const namedChannels = $derived(previewer.channels.filter((c) => c.name));

  // ── Scale bar ──────────────────────────────────────────────────────
  // Pick a "nice" round bar length that fits ~15-25% of the canvas width.

  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

  let scaleBar = $derived.by(() => {
    const { maxW, maxH } = channelBoundingBox(previewer.channels);
    if (maxW <= 0 || maxH <= 0 || fov.width <= 0) return null;

    const cw = containerSize.width;
    const ch = containerSize.height;
    if (cw <= 0 || ch <= 0) return null;

    // Compute draw area (same contain-fit as compositeTiledFrames)
    const vp = previewer.viewport;
    const vpAspect = (vp.w * maxW) / (vp.h * maxH);
    const canvasAspect = cw / ch;
    const drawW = canvasAspect > vpAspect ? ch * vpAspect : cw;

    // µm per CSS pixel
    const umPerPx = (vp.w * fov.width) / drawW;
    if (!Number.isFinite(umPerPx) || umPerPx <= 0) return null;

    // Target bar: ~20% of canvas width
    const targetUm = umPerPx * cw * 0.2;
    const barUm = NICE_STEPS.findLast((s) => s <= targetUm) ?? NICE_STEPS[0];
    const barPx = barUm / umPerPx;

    const label = barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm`;
    return { barPx, label };
  });
</script>

<div class="grid h-full grid-rows-[auto_1fr_auto] bg-canvas" bind:this={containerEl}>
  <!-- Top: Controls -->
  <div class="flex items-center justify-between p-4">
    <div class="flex h-ui-lg items-center gap-1">
      <button
        onclick={() => (showHistograms = !showHistograms)}
        class="flex cursor-pointer items-center justify-center rounded-full p-1 transition-colors hover:bg-element-hover {showHistograms
          ? 'text-fg-muted'
          : 'text-fg-muted/40'}"
        aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
        title={showHistograms ? 'Hide histograms' : 'Show histograms'}
      >
        <Bargraph width="14" height="14" />
      </button>
      <PreviewInfo {previewer} />
    </div>
    <PanZoomControls {previewer} />
  </div>

  <!-- Center: Canvas -->
  <div class="relative flex items-center justify-center overflow-hidden px-4" bind:this={canvasContainerEl}>
    <canvas bind:this={canvasEl} class="h-full w-full" class:is-idle={!previewer.isPreviewing}></canvas>
    {#if scaleBar}
      <div class="pointer-events-none absolute bottom-6 right-6 flex flex-col items-end gap-0.5">
        <span class="font-mono text-xs text-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">{scaleBar.label}</span>
        <div
          class="h-1 rounded-full bg-fg-muted drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
          style:width="{scaleBar.barPx}px"
        ></div>
      </div>
    {/if}
  </div>

  <!-- Bottom: Channel Histograms -->
  <div class="flex justify-around gap-8 p-4">
    {#if showHistograms}
      {#each namedChannels as channel (channel.idx)}
        <div class=" min-w-0 flex-1">
          <Histogram
            label={channel.label ?? channel.config?.label ?? channel.name ?? ''}
            histData={channel.latestHistogram}
            levelsMin={channel.levelsMin}
            levelsMax={channel.levelsMax}
            onLevelsChange={(min, max) => {
              if (channel.name) previewer.setChannelLevels(channel.name, min, max);
            }}
            colormap={channel.colormap}
            catalog={previewer.catalog}
            onColormapChange={(cmap) => {
              if (channel.name) previewer.setChannelColormap(channel.name, cmap);
            }}
            visible={channel.visible}
            onVisibilityChange={(v) => (channel.visible = v)}
          />
        </div>
      {/each}
    {/if}
  </div>
</div>
