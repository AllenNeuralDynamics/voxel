<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';

  import { Eye, EyeOff, VideoCamera } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { getPreviewContext } from '$lib/preview/session.svelte';
  import { pref } from '$lib/utils';

  import type { Bounds, Painter } from '../draw';
  import { getStageScene, type StageLayer, useLayer } from '../scene.svelte';

  // A hit means the pointer is over the live tile — enough to open the live view; it carries no data.
  type LiveHit = { readonly overTile: true };

  const app = getVoxelStation();
  const previews = getPreviewContext();
  const scene = getStageScene();
  const instrument = $derived(app.instrument);
  const preview = $derived(previews.current);
  const active = $derived(preview !== null && instrument?.mode !== 'idle');

  // Manual show/hide, remembered across sessions; gates the layer while preview or capture is active.
  const show = pref('stage:live-visible', true);
  let liveCanvas: HTMLCanvasElement;
  let rendering = false;
  let renderAgain = false;

  // The live FOV footprint (stage µm) centered on the current pose; null until pose + FOV are known.
  function liveBox(): Bounds | null {
    const stage = instrument?.stage;
    const fov = stage?.fov;
    const x = stage?.x?.position?.value;
    const y = stage?.y?.position?.value;
    if (x == null || y == null || !fov) return null;
    const [fw, fh] = fov;
    return { minX: x - fw / 2, minY: y - fh / 2, maxX: x + fw / 2, maxY: y + fh / 2 };
  }

  // Draw the live camera footprint as an opaque tile — channels blended additively among themselves, then
  // laid over the map so "now" wins over any snapshot/inpaint beneath. (The off-screen pointer back to the
  // pose lives in StageView's marker chrome, so it shows whether or not a preview is running.)
  const draw = (p: Painter) => {
    const box = liveBox();
    if (!box || !liveCanvas || !preview?.channels.some((channel) => channel.visible && channel.overviewFrame)) return;
    p.pass('source-over', (tile) => {
      tile.image(liveCanvas, box.minX, box.minY, box.maxX - box.minX, box.maxY - box.minY);
    });
  };

  async function renderLiveFrame() {
    if (!preview || !liveCanvas) return;
    if (rendering) {
      renderAgain = true;
      return;
    }
    rendering = true;
    try {
      do {
        renderAgain = false;
        liveCanvas.width = 1024;
        liveCanvas.height = Math.max(1, Math.round(1024 / preview.boundingBoxAspect));
        await preview.renderFull(liveCanvas);
      } while (renderAgain);
      scene.invalidate();
    } finally {
      rendering = false;
    }
  }

  function hitTest(world: [number, number]): LiveHit | null {
    const box = liveBox();
    if (!box) return null;
    const [x, y] = world;
    return x >= box.minX && x <= box.maxX && y >= box.minY && y <= box.maxY ? { overTile: true } : null;
  }

  function nativeScale(): number | null {
    const fov = instrument?.stage.fov;
    if (!preview || !fov || fov[0] <= 0 || fov[1] <= 0) return null;
    let best = 0;
    for (const channel of preview.channels) {
      if (!channel.visible || channel.sensorWidth <= 0) continue;
      best = Math.max(best, channel.sensorWidth / fov[0], channel.sensorHeight / fov[1]);
    }
    return best > 0 ? best : null;
  }

  const layer: StageLayer<LiveHit> = {
    id: 'live',
    z: 1, // "now" sits above snapshots (0) and inpaint (-1); the green pose marker is chrome above all
    get visible() {
      return active && show.get();
    },
    draw,
    hitTest,
    onActivate: () => app.viewMode.set('live'), // double-click the live tile → full live view
    menu: liveMenu,
    maxScale: nativeScale // zoom in to the camera's native resolution, no further
  };
  useLayer(layer);

  // Repaint on every new frame / detail view / channel change, and whenever visibility flips.
  watch(
    () => [preview?.redrawGeneration, active, show.get()] as const,
    () => void renderLiveFrame()
  );

  onMount(() => void renderLiveFrame());
</script>

{#snippet liveMenu()}
  <ContextMenu.Item onSelect={() => app.viewMode.set('live')}>
    <VideoCamera width="14" height="14" />
    Open live view
  </ContextMenu.Item>
{/snippet}

<div class="flex flex-col gap-0.5">
  <canvas bind:this={liveCanvas} class="hidden"></canvas>
  <div class="flex items-center gap-1 px-3 py-1">
    <span class="flex-1 text-sm tracking-wide text-fg-muted uppercase">Live</span>
    <button
      type="button"
      title={show.get() ? 'Hide live' : 'Show live'}
      aria-label={show.get() ? 'Hide live' : 'Show live'}
      class="focus-visible:ring-focused inline-flex size-ui-xs shrink-0 cursor-pointer items-center justify-center rounded text-fg-muted transition-colors hover:text-fg focus:outline-none focus-visible:ring-2"
      onclick={() => show.set(!show.get())}
    >
      {#if show.get()}<Eye width="14" height="14" />{:else}<EyeOff width="14" height="14" />{/if}
    </button>
  </div>
</div>
