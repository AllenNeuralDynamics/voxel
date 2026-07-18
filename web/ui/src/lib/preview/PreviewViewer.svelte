<script lang="ts">
  import { fade } from 'svelte/transition';

  import { getVoxelApp, type Preview } from '$lib/model';

  import PreviewCanvas from './PreviewCanvas.svelte';
  import SnapCanvas from './SnapCanvas.svelte';
  import SnapshotFlyOverlay from './SnapshotFlyOverlay.svelte';

  interface Props {
    previewer: Preview;
    fov: [number, number] | null;
  }

  let { previewer, fov }: Props = $props();

  const app = getVoxelApp();
  const view = app.view;

  // Whether the center shows saved content (Snaps mode) rather than the live stream.
  const showSnaps = $derived(view.mode === 'snaps');
</script>

<div class="flex h-full flex-col bg-canvas">
  <div class="relative flex-1 overflow-hidden" data-fly-origin>
    {#if showSnaps}
      <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
        <SnapCanvas />
      </div>
    {:else}
      <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
        <PreviewCanvas {previewer} {fov} />
      </div>
    {/if}
  </div>

  <SnapshotFlyOverlay />
</div>
