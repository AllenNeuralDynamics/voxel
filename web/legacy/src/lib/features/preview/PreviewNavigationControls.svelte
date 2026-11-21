<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';

  import { prefs } from '$lib/core/prefs';
  import { clampTopLeft } from '$lib/core/utils/vec';
  import { NumberBox } from '@voxel/kit';
  import { ChevronDown } from '@voxel/kit/icons';

  import { isFullViewport } from './render';
  import { DEFAULT_VIEWPORT, type PreviewSession, wheelZoomFactor } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  let { previewer }: Props = $props();

  const navigatorVisible = prefs.viewer.navigatorVisible;
  let minimapEl = $state<HTMLDivElement | null>(null);
  let canvasEl = $state<HTMLCanvasElement | null>(null);
  let drawing = false;
  let redraw = false;

  const canvasSize = new ElementSize(() => canvasEl);
  const minimapAspect = $derived.by(() => {
    const aspect = previewer.boundingBoxAspect;
    return Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
  });
  const viewportZoomed = $derived(!isFullViewport(previewer.viewport));

  async function drawMinimap() {
    if (!navigatorVisible.get() || !canvasEl) return;
    if (drawing) {
      redraw = true;
      return;
    }
    drawing = true;
    try {
      do {
        redraw = false;
        // The minimap can close while a draw is running, which removes the canvas.
        const canvas = canvasEl;
        if (!canvas || !navigatorVisible.get()) break;
        await previewer.renderFull(canvas);
      } while (redraw);
    } finally {
      drawing = false;
    }
  }

  watch(
    () => [canvasSize.width, canvasSize.height] as const,
    ([width, height]) => {
      if (!canvasEl || width <= 0 || height <= 0) return;
      const dpr = devicePixelRatio;
      canvasEl.width = Math.round(width * dpr);
      canvasEl.height = Math.round(height * dpr);
      void drawMinimap();
    }
  );

  watch(
    () => previewer.redrawGeneration,
    () => void drawMinimap()
  );

  onMount(() => void drawMinimap());

  let dragging = false;
  let startX = 0;
  let startY = 0;
  let startViewport = { ...DEFAULT_VIEWPORT };

  function pointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    startViewport = { ...previewer.viewport };
  }

  function pointerMove(e: PointerEvent) {
    if (!dragging || !minimapEl) return;
    const rect = minimapEl.getBoundingClientRect();
    const dx = (e.clientX - startX) / rect.width;
    const dy = (e.clientY - startY) / rect.height;
    const { w, h } = previewer.viewport;
    previewer.setViewport({
      x: clampTopLeft(startViewport.x + dx, w),
      y: clampTopLeft(startViewport.y + dy, h),
      w,
      h
    });
  }

  function pointerUp(e: PointerEvent) {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    dragging = false;
  }

  function recenter(e: PointerEvent) {
    if (e.button !== 0 || !minimapEl) return;
    const rect = minimapEl.getBoundingClientRect();
    const { w, h } = previewer.viewport;
    const x = (e.clientX - rect.left) / rect.width - w / 2;
    const y = (e.clientY - rect.top) / rect.height - h / 2;
    previewer.setViewport({ x: clampTopLeft(x, w), y: clampTopLeft(y, h), w, h });
  }

  function wheelZoom(e: WheelEvent) {
    e.preventDefault();
    const { x, y, w, h } = previewer.viewport;
    previewer.zoomBy(wheelZoomFactor(e), x + w / 2, y + h / 2, 0.5, 0.5);
  }
</script>

<div class="pointer-events-auto flex w-full flex-col overflow-hidden frame-overlay">
  <div class="flex items-center gap-0.75 p-1 font-mono text-base">
    <NumberBox model={previewer.panXModel} prefix="X" decimals={2} class="min-w-0 bg-transparent pr-0.5 pl-0" />
    <NumberBox model={previewer.panYModel} prefix="Y" decimals={2} class="min-w-0 bg-transparent pr-0.5 pl-0" />
    <NumberBox model={previewer.zoomModel} prefix="K" class="min-w-0 bg-transparent pr-0.5 pl-0" />
    <button
      type="button"
      onclick={() => navigatorVisible.set(!navigatorVisible.get())}
      class="flex h-6 w-4 shrink-0 cursor-pointer items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      aria-expanded={navigatorVisible.get()}
      aria-label={navigatorVisible.get() ? 'Hide navigator' : 'Show navigator'}
      title={navigatorVisible.get() ? 'Hide navigator' : 'Show navigator'}
    >
      <ChevronDown
        width="14"
        height="14"
        class="transition-transform {navigatorVisible.get() ? 'rotate-180' : '-rotate-90'}"
      />
    </button>
  </div>

  {#if navigatorVisible.get()}
    <div class="border-t border-line-muted p-1.5">
      <div
        bind:this={minimapEl}
        class="relative w-full overflow-hidden rounded-xs border border-line-faint"
        style:aspect-ratio={minimapAspect}
        onwheel={wheelZoom}
      >
        <canvas
          bind:this={canvasEl}
          role="button"
          tabindex={-1}
          aria-label="Recenter viewport"
          onpointerdown={recenter}
          class="absolute inset-0 size-full cursor-pointer"
        ></canvas>
        {#if viewportZoomed}
          <div
            role="slider"
            aria-label="Preview viewport"
            aria-valuenow={Math.round(previewer.viewport.x * 100)}
            tabindex="-1"
            class="absolute min-h-5 min-w-5 cursor-move border border-fg bg-tint halo transition-colors hover:bg-tint-hover"
            style:left="{previewer.viewport.x * 100}%"
            style:top="{previewer.viewport.y * 100}%"
            style:width="{previewer.viewport.w * 100}%"
            style:height="{previewer.viewport.h * 100}%"
            onpointerdown={pointerDown}
            onpointermove={pointerMove}
            onpointerup={pointerUp}
          ></div>
        {/if}
      </div>
    </div>
  {/if}
</div>
