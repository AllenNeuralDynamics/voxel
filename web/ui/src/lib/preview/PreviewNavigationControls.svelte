<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';

  import { ChevronDown } from '$lib/icons';
  import SpinBox from '$lib/prop/numeric/SpinBox.svelte';
  import { clampTopLeft, pref } from '$lib/utils';

  import { isFullViewport } from './render';
  import { DEFAULT_VIEWPORT, type PreviewSession, wheelZoomFactor } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  let { previewer }: Props = $props();

  const navigatorVisible = pref('preview:navigator-visible', true);
  let minimapEl = $state<HTMLDivElement | null>(null);
  let canvasEl = $state<HTMLCanvasElement | null>(null);
  let drawing = false;
  let redraw = false;

  const canvasSize = new ElementSize(() => canvasEl);
  const minimapAspect = $derived.by(() => {
    const aspect = previewer.boundingBoxAspect;
    return Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
  });
  const minimapFit = $derived(
    minimapAspect >= 1 ? { width: 100, height: 100 / minimapAspect } : { width: minimapAspect * 100, height: 100 }
  );
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
        await previewer.renderFull(canvasEl);
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

<div class="pointer-events-auto flex w-full flex-col overflow-hidden overlay-panel">
  {#if navigatorVisible.get()}
    <div class="border-b border-border p-1.5">
      <div class="relative aspect-square w-full overflow-hidden rounded-xs border border-border/40" onwheel={wheelZoom}>
        <div
          bind:this={minimapEl}
          class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 overflow-hidden"
          style:width="{minimapFit.width}%"
          style:height="{minimapFit.height}%"
        >
          <canvas
            bind:this={canvasEl}
            role="button"
            tabindex={-1}
            aria-label="Recenter viewport"
            onpointerdown={recenter}
            class="h-full w-full cursor-pointer"
          ></canvas>
          {#if viewportZoomed}
            <div
              role="slider"
              aria-label="Preview viewport"
              aria-valuenow={Math.round(previewer.viewport.x * 100)}
              tabindex="-1"
              class="absolute min-h-5 min-w-5 cursor-move border border-warning/80 bg-warning/10 transition-colors hover:bg-fg/15"
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
    </div>
  {/if}

  <div class="flex items-center gap-0.75 p-1 font-mono text-base">
    <SpinBox
      model={previewer.panXModel}
      prefix="X"
      decimals={2}
      numCharacters={4}
      align="right"
      steppers={false}
      class="min-w-0 bg-transparent pr-0.5 pl-0"
    />
    <SpinBox
      model={previewer.panYModel}
      prefix="Y"
      decimals={2}
      numCharacters={4}
      align="right"
      steppers={false}
      class="min-w-0 bg-transparent pr-0.5 pl-0"
    />
    <SpinBox
      model={previewer.zoomModel}
      prefix="K"
      decimals={2}
      numCharacters={6}
      align="right"
      class="min-w-0 bg-transparent pr-0.5 pl-0"
      steppers={false}
    />
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
</div>
