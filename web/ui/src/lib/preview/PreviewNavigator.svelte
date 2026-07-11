<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';

  import { compositeFullFrames, DEFAULT_VIEWPORT, type Preview, wheelZoomFactor } from '$lib/model';
  import { clampTopLeft } from '$lib/utils';

  import PanZoomControls from './PanZoomControls.svelte';

  interface Props {
    previewer: Preview;
    zoomBy: (factor: number, anchorX: number, anchorY: number, anchorFracX?: number, anchorFracY?: number) => void;
  }

  let { previewer, zoomBy }: Props = $props();

  let wrapperEl: HTMLDivElement;
  let canvasEl: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;

  const size = new ElementSize(() => wrapperEl);

  // The minimap matches the sensor bounding-box aspect so the full-frame composite fills it with
  // no letterboxing — which lets the viewport box map to plain normalized percentages.
  const aspect = $derived(previewer.boundingBoxAspect || 1);

  function draw() {
    if (ctx && canvasEl) compositeFullFrames(ctx, canvasEl, previewer.channels);
  }

  watch(
    () => [size.width, size.height] as const,
    ([w, h]) => {
      if (!canvasEl || w <= 0 || h <= 0) return;
      const dpr = devicePixelRatio;
      canvasEl.width = Math.round(w * dpr);
      canvasEl.height = Math.round(h * dpr);
      draw();
    }
  );

  watch(
    () => previewer.redrawGeneration,
    () => draw()
  );

  onMount(() => {
    ctx = canvasEl.getContext('2d');
    draw();
    // Non-passive so preventDefault can stop the page from scrolling while zooming the minimap.
    wrapperEl.addEventListener('wheel', wheelZoom, { passive: false });
    return () => wrapperEl.removeEventListener('wheel', wheelZoom);
  });

  // Drag the box to pan — pointer deltas in wrapper fractions map directly to viewport-origin deltas.
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let startVp = { ...DEFAULT_VIEWPORT };

  function pointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    startVp = { ...previewer.viewport };
    previewer.isPanZoomActive = true;
  }

  function pointerMove(e: PointerEvent) {
    if (!dragging) return;
    const rect = wrapperEl.getBoundingClientRect();
    const dx = (e.clientX - startX) / rect.width;
    const dy = (e.clientY - startY) / rect.height;
    const { w, h } = previewer.viewport;
    previewer.setViewport({ x: clampTopLeft(startVp.x + dx, w), y: clampTopLeft(startVp.y + dy, h), w, h });
    previewer.queueViewportUpdate({ ...previewer.viewport });
  }

  function pointerUp(e: PointerEvent) {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    dragging = false;
    previewer.isPanZoomActive = false;
    previewer.queueViewportUpdate({ ...previewer.viewport });
  }

  // Clicking the minimap (the box sits on top and handles its own drag) jumps the viewport center here.
  function recenter(e: PointerEvent) {
    if (e.button !== 0) return;
    const rect = wrapperEl.getBoundingClientRect();
    const { w, h } = previewer.viewport;
    const x = (e.clientX - rect.left) / rect.width - w / 2;
    const y = (e.clientY - rect.top) / rect.height - h / 2;
    previewer.setViewport({ x: clampTopLeft(x, w), y: clampTopLeft(y, h), w, h });
    previewer.queueViewportUpdate({ ...previewer.viewport });
  }

  // Scroll over the minimap to zoom around the current view center (position stays put; use click/drag to move).
  function wheelZoom(e: WheelEvent) {
    e.preventDefault();
    const { x, y, w, h } = previewer.viewport;
    zoomBy(wheelZoomFactor(e), x + w / 2, y + h / 2, 0.5, 0.5);
  }
</script>

<div
  class="pointer-events-auto flex w-fit max-w-62 flex-col gap-1.5 rounded-xs border border-border/50 bg-floating/90 p-1.5 shadow-lg backdrop-blur-sm"
>
  <div
    bind:this={wrapperEl}
    class="relative w-full overflow-hidden rounded-xs border border-border/40 bg-canvas/60"
    style:aspect-ratio={aspect}
  >
    <canvas
      bind:this={canvasEl}
      role="button"
      tabindex="-1"
      aria-label="Recenter viewport"
      onpointerdown={recenter}
      class="h-full w-full cursor-pointer"
    ></canvas>
    <div
      role="slider"
      aria-label="Preview viewport"
      aria-valuenow={Math.round(previewer.viewport.x * 100)}
      tabindex="-1"
      class="absolute min-h-5 min-w-5 cursor-move border border-fg/80 bg-fg/10 transition-colors hover:bg-fg/20"
      style:left="{previewer.viewport.x * 100}%"
      style:top="{previewer.viewport.y * 100}%"
      style:width="{previewer.viewport.w * 100}%"
      style:height="{previewer.viewport.h * 100}%"
      onpointerdown={pointerDown}
      onpointermove={pointerMove}
      onpointerup={pointerUp}
    ></div>
  </div>

  <PanZoomControls {previewer} />
</div>
