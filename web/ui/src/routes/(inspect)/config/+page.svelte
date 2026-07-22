<script lang="ts">
  import { defaultDialog } from '$lib/DefaultConfigDialog.svelte';
  import { Button, DiffJsonView, JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
</script>

<section class="flex h-full flex-col">
  <h2 class="mb-4 px-4 text-2xl text-fg">Configuration</h2>
  {#if instrument}
    <div class="flex-1 space-y-6 overflow-auto px-4">
      <div>
        <div class="mb-2 flex items-center gap-3">
          <h3 class="text-base font-medium tracking-wide text-fg-muted/70 uppercase">Bench</h3>
          <div class="ml-auto flex items-center gap-1.5">
            <Button variant="ghost" size="xs" onclick={() => defaultDialog.open('restore')}>Restore default</Button>
            <Button variant="outline" size="xs" onclick={() => defaultDialog.open('save')}>Save as default</Button>
          </div>
        </div>
        <DiffJsonView data={instrument.state} base={instrument.default} expandDepth={1} />
      </div>
      <div>
        <h3 class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Hardware</h3>
        <JsonView data={instrument.hal} expandDepth={1} />
      </div>
    </div>
  {/if}
</section>
