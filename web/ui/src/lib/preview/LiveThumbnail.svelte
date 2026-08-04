<script lang="ts">
  import { ElementSize, watch } from 'runed';
  import { onMount } from 'svelte';
  import type { HTMLCanvasAttributes } from 'svelte/elements';

  import { type Preview } from '$lib/model';

  interface Props extends HTMLCanvasAttributes {
    previewer: Preview;
  }

  // A bare canvas that renders the live full-frame composite and keeps its backing store sized to its box.
  // Consumers own the wrapper/aspect/overlays; extra attributes (class, role, onpointerdown…) pass through.
  let { previewer, ...rest }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let drawing = false;
  let redraw = false;

  const size = new ElementSize(() => canvasEl);

  async function draw() {
    if (!canvasEl) return;
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
    () => [size.width, size.height] as const,
    ([w, h]) => {
      if (!canvasEl || w <= 0 || h <= 0) return;
      const dpr = devicePixelRatio;
      canvasEl.width = Math.round(w * dpr);
      canvasEl.height = Math.round(h * dpr);
      void draw();
    }
  );

  watch(
    () => previewer.redrawGeneration,
    () => void draw()
  );

  onMount(() => {
    void draw();
  });
</script>

<canvas bind:this={canvasEl} {...rest}></canvas>
