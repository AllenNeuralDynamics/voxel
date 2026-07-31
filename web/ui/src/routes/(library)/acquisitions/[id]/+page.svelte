<script lang="ts">
  import { page } from '$app/state';
  import { JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';
  import { sanitizeString } from '$lib/utils';

  const app = getVoxelApp();
  const id = $derived(page.params.id);
  const manifest = $derived(app.acquisitions?.find((m) => m.id === id) ?? null);
</script>

<div class="flex h-full min-h-0 flex-col gap-2">
  <header class="flex shrink-0 items-center justify-between gap-4">
    <h1 class="truncate text-2xl font-medium text-fg">
      Acquisition {manifest && ' - ' + sanitizeString(manifest.instrument)}
    </h1>
    {#if manifest}
      <span class="shrink-0 rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">{manifest.status}</span>
    {/if}
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if manifest}
      <JsonView data={manifest} expandDepth={1} />
    {:else}
      <p class="text-fg-muted">Acquisition not found.</p>
    {/if}
  </div>
</div>
