<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';
  import type { HTMLCanvasAttributes } from 'svelte/elements';

  import { compositeFullFrames, type Preview } from '$lib/model';

  interface Props extends HTMLCanvasAttributes {
    previewer: Preview;
  }

  // A bare canvas that renders the live full-frame composite and keeps its backing store sized to its box.
  // Consumers own the wrapper/aspect/overlays; extra attributes (class, role, onpointerdown…) pass through.
  let { previewer, ...rest }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;

  const size = new ElementSize(() => canvasEl);

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
  });
</script>

<canvas bind:this={canvasEl} {...rest}></canvas>
