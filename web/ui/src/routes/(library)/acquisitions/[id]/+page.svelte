<script lang="ts">
  import { toast } from 'svelte-sonner';

  import { page } from '$app/state';
  import { Button, JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';
  import PresetNameDialog from '$lib/PresetNameDialog.svelte';
  import { sanitizeString } from '$lib/utils';

  const app = getVoxelApp();
  const id = $derived(page.params.id);
  const manifest = $derived(app.acquisitions?.find((m) => m.id === id) ?? null);
  let createPresetDialogOpen = $state(false);

  async function createPreset(name: string): Promise<void> {
    if (!manifest) return;
    const preset = await app.createPresetFromAcquisition(manifest.id, name);
    toast.success(`Created preset “${preset.name}”`);
  }
</script>

<div class="flex h-full min-h-0 flex-col gap-2">
  <header class="flex shrink-0 items-center justify-between gap-4">
    <h1 class="truncate text-2xl font-medium text-fg">
      Acquisition {manifest && ' - ' + sanitizeString(manifest.instrument)}
    </h1>
    <div class="flex shrink-0 items-center gap-2">
      {#if manifest}
        <span class="rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">{manifest.status}</span>
        <Button variant="outline" size="xs" onclick={() => (createPresetDialogOpen = true)}>Create preset…</Button>
      {/if}
    </div>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if manifest}
      <JsonView data={manifest} expandDepth={1} />
    {:else}
      <p class="text-fg-muted">Acquisition not found.</p>
    {/if}
  </div>
</div>

<PresetNameDialog
  bind:open={createPresetDialogOpen}
  title="Create Preset from Acquisition"
  description="Create a reusable preset from this acquisition's recorded bench configuration and tasks."
  onsubmit={createPreset}
/>
