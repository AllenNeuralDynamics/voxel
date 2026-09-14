<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { Group, Image as KonvaImage, Rect } from 'svelte-konva';
  import { toast } from 'svelte-sonner';

  import { VideoCamera } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import type { PreviewSession } from '$lib/preview/session.svelte';

  import { getStageContext } from './context.svelte';
  import { type Bounds, worldTransform } from './geometry';

  let {
    preview,
    bounds,
    active = true,
    visible = $bindable(true),
    onactivate
  }: {
    preview: PreviewSession | null;
    bounds: Bounds | null;
    active?: boolean;
    visible?: boolean;
    onactivate?: () => void;
  } = $props();

  const context = getStageContext();
  const available = $derived(
    active && visible && !!preview?.channels.some((channel) => channel.visible && channel.overviewFrame)
  );
  let tile = $state<KonvaImage>();
  let footprint = $state<Rect>();
  let canvas = $state.raw<HTMLCanvasElement | null>(null);
  let rendered = $state.raw<PreviewSession | null>(null);
  let source: HTMLCanvasElement;
  let pending: PreviewSession | null = null;
  let rendering = false;
  let disposed = false;
  let lastError: string | null = null;

  async function render() {
    if (rendering || !canvas) return;
    rendering = true;
    try {
      while (pending && !disposed) {
        const session = pending;
        pending = null;
        source.width = 1024;
        source.height = Math.max(1, Math.round(1024 / session.boundingBoxAspect));
        try {
          await session.renderFull(source);
          if (disposed || session !== preview || !available) continue;
          if (canvas.width !== source.width) canvas.width = source.width;
          if (canvas.height !== source.height) canvas.height = source.height;
          const pixels = canvas.getContext('2d');
          if (!pixels) throw new Error('Could not create the live image canvas.');
          // Keep a stable copy: WebGPU's canvas may be cleared before Konva's next draw.
          pixels.fillStyle = '#000';
          pixels.fillRect(0, 0, canvas.width, canvas.height);
          pixels.drawImage(source, 0, 0);
          rendered = session;
          tile?.node.getLayer()?.batchDraw();
          lastError = null;
        } catch (error) {
          if (disposed || session !== preview) continue;
          rendered = null;
          const message = error instanceof Error ? error.message : String(error);
          if (message !== lastError) toast.error(`Konva live preview: ${message}`);
          lastError = message;
        }
      }
    } finally {
      rendering = false;
      if (disposed) source.getContext('webgpu')?.unconfigure();
    }
  }

  $effect(() => {
    const session = preview;
    void session?.redrawGeneration;
    const enabled = available;
    if (!canvas) return;
    untrack(() => {
      pending = enabled ? session : null;
      if (!enabled) rendered = null;
      void render();
    });
  });

  onMount(() => {
    source = document.createElement('canvas');
    canvas = document.createElement('canvas');
    const unregister = context.register({
      id: 'live',
      label: 'Live FOV',
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      },
      menu: (selection) =>
        onactivate && 'hits' in selection && footprint && selection.hits.includes(footprint.node) ? liveMenu : undefined
    });
    return () => {
      disposed = true;
      pending = null;
      unregister();
      if (!rendering) source.getContext('webgpu')?.unconfigure();
    };
  });
</script>

{#snippet liveMenu()}
  <ContextMenu.Item onSelect={() => onactivate?.()}>
    <VideoCamera width="14" height="14" />
    Open field of view
  </ContextMenu.Item>
{/snippet}

<Group {...worldTransform(context.view.scale, context.orientation)}>
  {#if available && bounds && canvas && rendered === preview}
    <KonvaImage
      bind:this={tile}
      image={canvas}
      x={context.orientation.x > 0 ? bounds.minX : bounds.maxX}
      y={context.orientation.y > 0 ? bounds.maxY : bounds.minY}
      scaleX={context.orientation.x}
      scaleY={-context.orientation.y}
      width={bounds.maxX - bounds.minX}
      height={bounds.maxY - bounds.minY}
      listening={false}
    />
  {/if}
  {#if visible && bounds && onactivate}
    <Rect
      bind:this={footprint}
      x={bounds.minX}
      y={bounds.minY}
      width={bounds.maxX - bounds.minX}
      height={bounds.maxY - bounds.minY}
      fill="transparent"
      onpointerdblclick={() => onactivate?.()}
    />
  {/if}
</Group>
