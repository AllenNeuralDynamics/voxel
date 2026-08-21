<script lang="ts">
  import { toast } from 'svelte-sonner';

  import { page } from '$app/state';
  import { Button, JsonView } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import PresetNameDialog from '$lib/PresetNameDialog.svelte';

  const app = getVoxelStation();
  const instrumentId = $derived(page.params.instrumentId);
  const acquisitionId = $derived(page.params.acquisitionId);
  const manifest = $derived(
    app.acquisitions.find((candidate) => candidate.id === acquisitionId && candidate.instrument === instrumentId) ??
      null
  );
  let createPresetDialogOpen = $state(false);

  async function createPreset(name: string): Promise<void> {
    if (!manifest) return;
    const preset = await app.createPresetFromAcquisition(manifest.id, name);
    toast.success(`Created preset “${preset.name}”`);
  }
</script>

<div class="flex min-h-full flex-col gap-2 p-4">
  {#if manifest}
    <div class="flex shrink-0 items-center justify-end gap-2">
      <span class="rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">{manifest.status}</span>
      <Button variant="outline" size="xs" onclick={() => (createPresetDialogOpen = true)}>Create preset…</Button>
    </div>
  {/if}

  <div class="min-h-0 flex-1">
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
  description="Create a reusable preset from this acquisition's recorded instrument state and tasks."
  onsubmit={createPreset}
/>
