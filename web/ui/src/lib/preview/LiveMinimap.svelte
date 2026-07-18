<script lang="ts">
  import { onMount } from 'svelte';

  import { DEFAULT_VIEWPORT, type Preview, wheelZoomFactor } from '$lib/model';
  import { clampTopLeft } from '$lib/utils';

  import LiveThumbnail from './LiveThumbnail.svelte';

  interface Props {
    previewer: Preview;
  }

  let { previewer }: Props = $props();

  let wrapperEl: HTMLDivElement;

  // The minimap matches the sensor bounding-box aspect so the full-frame composite fills it with
  // no letterboxing — which lets the viewport box map to plain normalized percentages.
  const aspect = $derived(previewer.boundingBoxAspect || 1);

  onMount(() => {
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
    previewer.zoomBy(wheelZoomFactor(e), x + w / 2, y + h / 2, 0.5, 0.5);
  }
</script>

<div
  bind:this={wrapperEl}
  class="relative w-full overflow-hidden rounded-xs border border-border/40 bg-canvas/60"
  style:aspect-ratio={aspect}
>
  <LiveThumbnail
    {previewer}
    role="button"
    tabindex={-1}
    aria-label="Recenter viewport"
    onpointerdown={recenter}
    class="h-full w-full cursor-pointer"
  />
  <div
    role="slider"
    aria-label="Preview viewport"
    aria-valuenow={Math.round(previewer.viewport.x * 100)}
    tabindex="-1"
    class="absolute min-h-5 min-w-5 cursor-move border border-warning/80 bg-warning/10 transition-colors hover:bg-fg/20"
    style:left="{previewer.viewport.x * 100}%"
    style:top="{previewer.viewport.y * 100}%"
    style:width="{previewer.viewport.w * 100}%"
    style:height="{previewer.viewport.h * 100}%"
    onpointerdown={pointerDown}
    onpointermove={pointerMove}
    onpointerup={pointerUp}
  ></div>
</div>
