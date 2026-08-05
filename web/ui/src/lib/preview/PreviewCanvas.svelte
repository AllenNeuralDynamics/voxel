<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';

  import { clampTopLeft } from '$lib/utils';

  import PreviewNavigationControls from './PreviewNavigationControls.svelte';
  import { channelBoundingBox } from './render';
  import { type PreviewSession, wheelZoomFactor } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
    /** Field of view as a `[width, height]` µm tuple (`instrument.fov`), or null when unavailable. */
    fov: [number, number] | null;
  }

  let { previewer, fov }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let canvasContainerEl: HTMLDivElement;
  let isRendering = false;
  let needsRedraw = false;
  let drawPending = false;
  let animFrameId: number | null = null;

  // Live container size, measured from the DOM each frame (see syncSize).
  let viewW = $state(0);
  let viewH = $state(0);

  watch(
    () => previewer.redrawGeneration,
    () => {
      needsRedraw = true;
    }
  );

  // Measure the container from the DOM and keep the backing store + model aspect in sync. A ResizeObserver
  // can latch a 0 size when this canvas remounts inside the mode-switch fade; clientWidth never does.
  function syncSize() {
    if (!canvasContainerEl || !canvasEl) return;
    const w = canvasContainerEl.clientWidth;
    const h = canvasContainerEl.clientHeight;
    if (w === viewW && h === viewH) return;
    viewW = w;
    viewH = h;
    if (w <= 0 || h <= 0) return;
    previewer.setDisplayAspect(w / h);
    const dpr = devicePixelRatio;
    canvasEl.width = Math.round(w * dpr);
    canvasEl.height = Math.round(h * dpr);
    needsRedraw = true;
  }

  // Pan/zoom on the canvas element itself, so overlay siblings (controls, navigator) never trip it.
  function setupPanZoom(el: HTMLCanvasElement): () => void {
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let startViewport = { ...previewer.viewport };

    const pointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      el.setPointerCapture(e.pointerId);
      isPanning = true;
      panStartX = e.clientX;
      panStartY = e.clientY;
      startViewport = { ...previewer.viewport };
    };

    const pointerMove = (e: PointerEvent) => {
      if (!isPanning) return;
      const rect = el.getBoundingClientRect();
      const dx = ((e.clientX - panStartX) / rect.width) * previewer.viewport.w;
      const dy = ((e.clientY - panStartY) / rect.height) * previewer.viewport.h;
      const newX = clampTopLeft(startViewport.x - dx, previewer.viewport.w);
      const newY = clampTopLeft(startViewport.y - dy, previewer.viewport.h);
      previewer.setViewport({ x: newX, y: newY, w: previewer.viewport.w, h: previewer.viewport.h });
    };

    const pointerUp = (e: PointerEvent) => {
      if (e.button !== 0) return;
      el.releasePointerCapture(e.pointerId);
      isPanning = false;
    };

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const vp = previewer.viewport;
      // Keep the sensor point under the cursor fixed on screen.
      const mouseX = (e.clientX - rect.left) / rect.width;
      const mouseY = (e.clientY - rect.top) / rect.height;
      previewer.zoomBy(wheelZoomFactor(e), vp.x + mouseX * vp.w, vp.y + mouseY * vp.h, mouseX, mouseY);
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
    };
  }

  function frameLoop() {
    if (!isRendering) return;
    syncSize();
    if (needsRedraw && !drawPending && canvasEl) void draw();
    animFrameId = requestAnimationFrame(frameLoop);
  }

  async function draw() {
    drawPending = true;
    try {
      do {
        needsRedraw = false;
        await previewer.render(canvasEl);
      } while (needsRedraw && isRendering);
    } catch (error) {
      console.error('[preview] WebGPU render failed:', error);
    } finally {
      drawPending = false;
    }
  }

  onMount(() => {
    syncSize(); // seed size + aspect before the first frame
    isRendering = true;
    frameLoop();

    const teardown = setupPanZoom(canvasEl);
    return () => {
      isRendering = false;
      if (animFrameId !== null) cancelAnimationFrame(animFrameId);
      teardown();
    };
  });

  // ── Scale bar ──
  // Pick a "nice" round bar length that fits ~15-25% of the canvas width.
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

  const scaleBar = $derived.by(() => {
    const { maxW, maxH } = channelBoundingBox(previewer.channels);
    const [fovW, fovH] = fov ?? [0, 0];
    if (maxW <= 0 || maxH <= 0 || fovW <= 0 || fovH <= 0) return null;

    const cw = viewW;
    const ch = viewH;
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
</script>

{#snippet scaleBarBadge(bar: { barPx: number; label: string } | null)}
  <span class="font-mono text-fg">{bar?.label ?? '--'}</span>
  <div class="h-2 rounded-full bg-fg" style:width="{bar?.barPx ?? 0}px"></div>
{/snippet}

<div class="relative h-full w-full" bind:this={canvasContainerEl}>
  <canvas bind:this={canvasEl} class="h-full w-full"></canvas>

  {#if previewer.error}
    <div class="absolute inset-x-4 top-16 z-10 rounded border border-danger/40 bg-canvas/90 px-3 py-2 text-danger">
      {previewer.error}
    </div>
  {/if}

  <div class="pointer-events-none absolute bottom-4 left-4 z-10 w-58">
    <PreviewNavigationControls {previewer} />
  </div>

  <!-- Isolated scale bar. -->
  <div
    class="canvas-overlay-halo pointer-events-none absolute right-4 bottom-4 z-10 flex h-6 flex-col items-end justify-end gap-0.5"
  >
    {#if scaleBar}
      {@render scaleBarBadge(scaleBar)}
    {:else}
      {@render scaleBarBadge(null)}
    {/if}
  </div>
</div>

<style>
  .canvas-overlay-halo {
    filter: drop-shadow(0 1px 1px color-mix(in oklch, var(--color-canvas) 90%, transparent))
      drop-shadow(0 0 2px color-mix(in oklch, var(--color-canvas) 75%, transparent));
  }
</style>
