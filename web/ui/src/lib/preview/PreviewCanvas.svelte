<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';

  import { compositeViewFrames, type Preview } from '$lib/model';

  interface Props {
    previewer: Preview;
  }

  let { previewer }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let canvasContainerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let isRendering = false;
  let needsRedraw = false;
  let animFrameId: number | null = null;

  // Track the canvas container size to keep the backing store at device-pixel resolution.
  const containerSize = new ElementSize(() => canvasContainerEl);

  watch(
    () => previewer.redrawGeneration,
    () => {
      needsRedraw = true;
    }
  );

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

  onMount(() => {
    // Seed canvas size from layout before the ResizeObserver first fires.
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

    return () => {
      isRendering = false;
      if (animFrameId !== null) cancelAnimationFrame(animFrameId);
    };
  });
</script>

<div class="h-full w-full" bind:this={canvasContainerEl}>
  <canvas bind:this={canvasEl} class="h-full w-full"></canvas>
</div>
