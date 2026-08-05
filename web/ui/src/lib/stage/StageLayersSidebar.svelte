<script lang="ts">
  import { getVoxelApp } from '$lib/model';

  import Inpaint from './features/Inpaint.svelte';
  import Live from './features/Live.svelte';
  import Snapshots from './features/Snapshots.svelte';

  const app = getVoxelApp();
  const features = $derived(app.discovery.preview.features);
</script>

<div class="flex flex-col gap-4">
  <Live />
  {#if features.includes('inpainting')}<Inpaint />{/if}
  {#if features.includes('snapshots')}<Snapshots />{/if}
</div>
