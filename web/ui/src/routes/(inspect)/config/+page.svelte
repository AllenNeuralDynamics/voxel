<script lang="ts">
  import { JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const config = $derived(instrument ? { hal: instrument.hal, bench: instrument.state } : null);
</script>

<section class="px-4 pt-2 pb-4">
  <h2 class="mb-4 text-base font-medium text-fg">Configuration</h2>
  <JsonView data={config} expandDepth={2} />
</section>
