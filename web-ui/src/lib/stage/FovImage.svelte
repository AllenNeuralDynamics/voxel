<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { Image } from 'svelte-konva';
  import { toast } from 'svelte-sonner';

  import type { PreviewChannel, PreviewSession } from '$lib/preview/session.svelte';

  import { getStageContext } from './context.svelte';

  let {
    preview,
    channel,
    rect,
    onactivate
  }: {
    preview: PreviewSession;
    channel: PreviewChannel;
    rect: { x: number; y: number; width: number; height: number };
    onactivate?: () => void;
  } = $props();

  const context = getStageContext();
  let tile = $state<Image>();
  let pixels = $state.raw<CanvasRenderingContext2D | null>(null);
  let rendered = $state.raw<typeof rect | null>(null);
  let source: HTMLCanvasElement;
  let pending = false;
  let rendering = false;
  let disposed = false;
  let lastError: string | null = null;

  async function render() {
    if (rendering || !pixels) return;
    const canvas = pixels.canvas;
    rendering = true;
    try {
      while (pending && !disposed) {
        pending = false;
        const frame = channel.overviewFrame;
        if (!frame) continue;
        const placement = rect;
        source.height = Math.max(1, Math.round(1024 / preview.boundingBoxAspect));
        try {
          await preview.renderFull(source, channel);
          if (disposed || channel.overviewFrame !== frame) continue;
          if (canvas.height !== source.height) canvas.height = source.height;
          // Keep a stable copy: WebGPU's canvas may be cleared before Konva's next draw.
          pixels.clearRect(0, 0, canvas.width, canvas.height);
          pixels.drawImage(source, 0, 0);
          rendered = placement;
          tile?.node.getLayer()?.batchDraw();
          lastError = null;
        } catch (error) {
          if (disposed) continue;
          rendered = null;
          const message = error instanceof Error ? error.message : String(error);
          if (message !== lastError) toast.error(`FOV image: ${message}`);
          lastError = message;
        }
      }
    } finally {
      rendering = false;
      if (disposed) source.getContext('webgpu')?.unconfigure();
    }
  }

  $effect(() => {
    void preview.redrawGeneration;
    if (!pixels) return;
    untrack(() => {
      pending = true;
      void render();
    });
  });

  onMount(() => {
    source = document.createElement('canvas');
    const canvas = document.createElement('canvas');
    source.width = canvas.width = 1024;
    pixels = canvas.getContext('2d');
    if (!pixels) toast.error('Could not create the FOV image canvas.');
    return () => {
      disposed = true;
      pending = false;
      if (!rendering) source.getContext('webgpu')?.unconfigure();
    };
  });
</script>

{#if pixels && rendered}
  <Image
    bind:this={tile}
    image={pixels.canvas}
    {...rendered}
    x={rendered.x + (context.orientation.x > 0 ? 0 : rendered.width)}
    y={rendered.y + (context.orientation.y > 0 ? rendered.height : 0)}
    scaleX={context.orientation.x}
    scaleY={-context.orientation.y}
    globalCompositeOperation="lighter"
    onpointerdblclick={() => onactivate?.()}
  />
{/if}
