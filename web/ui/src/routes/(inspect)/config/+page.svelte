<script lang="ts">
  import { JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const config = $derived(instrument ? { hal: instrument.hal, bench: instrument.state } : null);
</script>

<section class="flex h-full flex-col">
  <h2 class="mb-4 px-4 text-2xl text-fg-muted">Configuration</h2>
  <div class="flex-1 overflow-auto px-4">
    <JsonView data={config} expandDepth={2} />
  </div>
</section>
