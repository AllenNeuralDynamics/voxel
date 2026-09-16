<script lang="ts">
  import { watch } from 'runed';
  import { onDestroy } from 'svelte';
  import { toast } from 'svelte-sonner';

  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Button } from '$lib/kit';
  import { errorMessage, getVoxelStation, type PresetRecord } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import PresetNameDialog from '$lib/PresetNameDialog.svelte';
  import { cn } from '$lib/utils';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const id = $derived(page.params.instrumentId ?? '');
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  let presets = $state.raw<PresetRecord[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let requestId = 0;
  let saveDialogOpen = $state(false);
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const sorted = $derived(
    presets.toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
  );

  onDestroy(() => {
    requestId++;
  });

  watch(
    () => id,
    (instrumentName) => {
      presets = [];
      saveDialogOpen = false;
      if (instrumentName) void refreshPresets(instrumentName);
    }
  );

  async function refreshPresets(instrumentName = id): Promise<void> {
    if (!instrumentName) return;
    const request = ++requestId;
    loading = true;
    loadError = null;
    try {
      const loaded = await app.fetchPresets(instrumentName);
      if (request === requestId && id === instrumentName) presets = loaded;
    } catch (error) {
      if (request === requestId && id === instrumentName) loadError = errorMessage(error);
    } finally {
      if (request === requestId && id === instrumentName) loading = false;
    }
  }

  async function saveCurrent(name: string): Promise<void> {
    if (!activeInstrument) throw new Error('Open the instrument before saving a preset.');
    const instrument = activeInstrument;
    const created = await instrument.savePreset(name);
    toast.success(`Saved preset “${created.name}”`);
    if (instrument.id === id) await refreshPresets();
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Presets' }]}>
    {#snippet trailing()}
      {#if activeInstrument}
        <Button variant="outline" size="xs" onclick={() => (saveDialogOpen = true)}>Save current…</Button>
      {/if}
    {/snippet}
  </PageHeader>
  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if id}
      {#key id}
        <div class="flex min-h-full flex-col gap-3 px-4 pb-4">
          {#if loading}
            <p class="py-8 text-center text-fg-muted" role="status">Loading presets…</p>
          {:else if loadError}
            <div class="flex flex-col items-center gap-3 rounded-lg border border-line-muted p-6">
              <p class="text-fg-muted" role="alert">Unable to load presets: {loadError}</p>
              <Button variant="outline" size="xs" onclick={() => refreshPresets()}>Retry</Button>
            </div>
          {:else if sorted.length > 0}
            <div class="overflow-hidden rounded-lg border border-line-muted bg-card">
              {#each sorted as preset, index (preset.id)}
                <a
                  href={resolve('/stations/[stationId]/instruments/[instrumentId]/presets/[presetId]', {
                    stationId,
                    instrumentId: id,
                    presetId: preset.id
                  })}
                  class={cn(
                    'block px-4 py-3 transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-border-focused',
                    index > 0 && 'border-t border-line-faint'
                  )}
                >
                  <span class="flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <span class="min-w-0 truncate text-fg">{preset.name}</span>
                    <span class="shrink-0 text-sm text-fg-muted">{dateFormat.format(new Date(preset.created_at))}</span>
                  </span>
                  <span class="mt-1 block text-sm text-fg-muted">
                    {Object.keys(preset.value.imaging.profiles).length} profiles ·
                    {Object.keys(preset.value.imaging.channels).length} channels ·
                    {Object.keys(preset.value.tasks).length} planned tasks
                  </span>
                </a>
              {/each}
            </div>
          {:else}
            <div class="rounded-lg border border-dashed border-line-muted px-4 py-8 text-center text-fg-muted">
              No presets have been saved for this instrument.
            </div>
          {/if}
        </div>

        <PresetNameDialog
          bind:open={saveDialogOpen}
          title="Save Current State as Preset"
          description="Save the current reusable configuration and acquisition tasks as a new preset."
          submitLabel="Save Preset"
          onsubmit={saveCurrent}
        />
      {/key}
    {/if}
  </div>
</div>
