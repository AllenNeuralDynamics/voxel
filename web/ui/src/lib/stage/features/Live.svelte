<script lang="ts">
  import { PersistedState, watch } from 'runed';

  import { Eye, EyeOff, VideoCamera } from '$lib/icons';
  import { Button, ContextMenu } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';

  import type { Bounds, Painter } from '../draw';
  import { getStageScene, type StageLayer, useLayer } from '../scene.svelte';

  // A hit means the pointer is over the live tile — enough to open the live view; it carries no data.
  type LiveHit = { readonly overTile: true };

  const app = getVoxelApp();
  const scene = getStageScene();
  const instrument = $derived(app.instrument);
  const preview = $derived(instrument?.preview ?? null);
  const previewing = $derived(preview?.isPreviewing ?? false);

  // Manual show/hide, remembered across sessions; gates the layer on top of `isPreviewing`.
  const show = new PersistedState('voxel-stage-live-visible', true);

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
    const frames = preview?.liveFrames() ?? [];
    if (frames.length === 0) return;
    p.pass('source-over', (tile) => {
      for (const f of frames) {
        tile.pass('lighter', (acc) => {
          acc.image(f.overview.src, f.overview.rect.x, f.overview.rect.y, f.overview.rect.w, f.overview.rect.h);
          if (f.detail) acc.image(f.detail.src, f.detail.rect.x, f.detail.rect.y, f.detail.rect.w, f.detail.rect.h);
        });
      }
    });
  };

  function hitTest(world: [number, number]): LiveHit | null {
    const box = liveBox();
    if (!box) return null;
    const [x, y] = world;
    return x >= box.minX && x <= box.maxX && y >= box.minY && y <= box.maxY ? { overTile: true } : null;
  }

  const layer: StageLayer<LiveHit> = {
    id: 'live',
    z: 1, // "now" sits above snapshots (0) and inpaint (-1); the green pose marker is chrome above all
    get visible() {
      return previewing && show.current;
    },
    draw,
    hitTest,
    onActivate: () => app.view.goLive(), // double-click the live tile → full live view
    menu: liveMenu,
    maxScale: () => preview?.nativeScale() ?? null // zoom in to the camera's native resolution, no further
  };
  useLayer(layer);

  // Repaint on every new frame / detail view / channel change, and whenever visibility flips.
  watch(
    () => [preview?.redrawGeneration, previewing, show.current] as const,
    () => scene.invalidate()
  );
</script>

{#snippet liveMenu()}
  <ContextMenu.Item onSelect={() => app.view.goLive()}>
    <VideoCamera width="14" height="14" />
    Open live view
  </ContextMenu.Item>
{/snippet}

<div class="flex flex-col gap-0.5">
  <div class="flex items-center gap-1 px-3 py-1">
    <span class="flex-1 text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Live</span>
    <Button
      variant="ghost"
      size="icon-xs"
      title={show.current ? 'Hide live' : 'Show live'}
      onclick={() => (show.current = !show.current)}
    >
      {#if show.current}<Eye width="16" height="16" />{:else}<EyeOff width="16" height="16" />{/if}
    </Button>
  </div>
</div>
