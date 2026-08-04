<script lang="ts">
  import { getVoxelApp } from '$lib/model';

  import Inpaint from './features/Inpaint.svelte';
  import Live from './features/Live.svelte';
  import Snapshots from './features/Snapshots.svelte';

  const { collapsed }: { collapsed: boolean } = $props();
  const app = getVoxelApp();
  const features = $derived(app.discovery.preview.features);
</script>

<aside
  class="shrink-0 overflow-hidden bg-surface transition-[width] duration-200 {collapsed
    ? 'w-0'
    : 'w-64 border-l border-border'}"
>
  <div
    class="flex h-full w-full flex-col gap-4 overflow-y-auto px-0 py-1.5 transition-opacity {collapsed
      ? 'invisible opacity-0'
      : 'opacity-100'}"
  >
    <Live />
    {#if features.includes('inpainting')}<Inpaint />{/if}
    {#if features.includes('snapshots')}<Snapshots />{/if}
  </div>
</aside>
