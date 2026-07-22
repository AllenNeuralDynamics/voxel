<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  import { channelBoundingBox, compositeViewFrames, type Preview, wheelZoomFactor } from '$lib/model';
  import SpinBox from '$lib/prop/numeric/SpinBox.svelte';
  import { clampTopLeft } from '$lib/utils';

  import LiveMinimap from './LiveMinimap.svelte';
  import PreviewControls from './PreviewControls.svelte';

  interface Props {
    previewer: Preview;
    /** Field of view as a `[width, height]` µm tuple (`instrument.fov`), or null when unavailable. */
    fov: [number, number] | null;
  }

  let { previewer, fov }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let canvasContainerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let isRendering = false;
  let needsRedraw = false;
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
    previewer.displayAspect = w / h; // keep the model's aspect current for zoomBy
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
      e.preventDefault();
      previewer.isPanZoomActive = true;
      const rect = el.getBoundingClientRect();
      const vp = previewer.viewport;
      // Keep the sensor point under the cursor fixed on screen.
      const mouseX = (e.clientX - rect.left) / rect.width;
      const mouseY = (e.clientY - rect.top) / rect.height;
      previewer.zoomBy(wheelZoomFactor(e), vp.x + mouseX * vp.w, vp.y + mouseY * vp.h, mouseX, mouseY);
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

  function frameLoop() {
    if (!isRendering) return;
    syncSize();
    if (needsRedraw && ctx && canvasEl) {
      needsRedraw = false;
      compositeViewFrames(ctx, canvasEl, previewer.channels, previewer.viewport);
    }
    animFrameId = requestAnimationFrame(frameLoop);
  }

  onMount(() => {
    ctx = canvasEl.getContext('2d');
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

  // Navigator locates the live viewport when zoomed in.
  const hasFrames = $derived(previewer.channels.some((ch) => ch.visible && ch.frame));
  const zoomed = $derived(previewer.viewport.w < 1 || previewer.viewport.h < 1);
  const showNavigator = $derived(hasFrames && zoomed);
</script>

{#snippet scaleBarBadge(bar: { barPx: number; label: string } | null)}
  <span class="font-mono text-fg-muted">{bar?.label ?? '--'}</span>
  <div class="h-1 rounded-full bg-fg-muted" style:width="{bar?.barPx ?? 0}px"></div>
{/snippet}

<div class="relative h-full w-full" bind:this={canvasContainerEl}>
  <canvas bind:this={canvasEl} class="h-full w-full"></canvas>

  <!-- Left overlay: preview controls (live-only — this canvas renders only in Live mode) -->
  <div class="absolute bottom-4 left-4 z-10">
    <PreviewControls {previewer} />
  </div>

  <!-- Right overlay: viewport minimap (when zoomed) + always-on pan/zoom controls, above the scale bar -->
  <div class="pointer-events-none absolute right-4 bottom-4 z-10 flex flex-col items-end gap-1.5">
    <div
      class="pointer-events-auto flex w-fit max-w-62 flex-col gap-1.5 rounded-xs border border-border/50 bg-floating/90 p-1.5 shadow-lg backdrop-blur-sm"
    >
      {#if showNavigator}
        <div transition:fade={{ duration: 150 }}>
          <LiveMinimap {previewer} />
        </div>
      {/if}
      <div class="flex items-center gap-1.5 font-mono">
        <SpinBox
          model={previewer.zoomModel}
          prefix="Zoom"
          decimals={2}
          numCharacters={6}
          align="right"
          steppers={false}
        />
        <SpinBox model={previewer.panXModel} prefix="X" decimals={2} numCharacters={5} align="right" steppers={false} />
        <SpinBox model={previewer.panYModel} prefix="Y" decimals={2} numCharacters={5} align="right" steppers={false} />
      </div>
    </div>

    <!-- Fixed height so the controls above never shift as the scale bar toggles -->
    <div class="canvas-overlay-halo flex h-6 flex-col items-end justify-end gap-0.5">
      {#if scaleBar}
        {@render scaleBarBadge(scaleBar)}
      {:else}
        {@render scaleBarBadge(null)}
      {/if}
    </div>
  </div>
</div>

<style>
  .canvas-overlay-halo {
    filter: drop-shadow(0 1px 1px color-mix(in oklch, var(--color-canvas) 90%, transparent))
      drop-shadow(0 0 2px color-mix(in oklch, var(--color-canvas) 75%, transparent));
  }
</style>
