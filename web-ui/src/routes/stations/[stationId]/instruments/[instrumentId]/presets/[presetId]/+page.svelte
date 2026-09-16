<script lang="ts">
  import { watch } from 'runed';
  import { onDestroy } from 'svelte';
  import { toast } from 'svelte-sonner';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Button, Dialog, JsonView } from '$lib/kit';
  import { ApiError, errorMessage, getVoxelStation, type PresetRecord } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const routeParams = $derived({ stationId, instrumentId });
  const presetId = $derived(page.params.presetId);
  const activeInstrument = $derived(instrumentId && app.activeName === instrumentId ? app.instrument : null);
  let selected = $state.raw<PresetRecord | null>(null);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let requestId = 0;
  let applyDialogOpen = $state(false);
  let deleteDialogOpen = $state(false);
  let busy = $state(false);

  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const breadcrumbItems = $derived([
    { label: 'Presets', href: resolve('/stations/[stationId]/instruments/[instrumentId]/presets', routeParams) },
    { label: selected?.name ?? (loading ? 'Loading preset…' : 'Preset'), title: presetId }
  ]);

  watch(
    () => [instrumentId, presetId] as const,
    ([instrumentName, targetId]) => {
      applyDialogOpen = false;
      deleteDialogOpen = false;
      void loadPreset(instrumentName, targetId);
    }
  );

  onDestroy(() => {
    requestId++;
  });

  async function loadPreset(instrumentName = instrumentId, targetId = presetId): Promise<void> {
    const request = ++requestId;
    selected = null;
    loadError = null;
    loading = true;
    try {
      if (!instrumentName || !targetId) return;
      const preset = await app.fetchPreset(instrumentName, targetId);
      if (request === requestId) selected = preset;
    } catch (error) {
      if (request === requestId && !(error instanceof ApiError && error.status === 404)) {
        loadError = errorMessage(error);
      }
    } finally {
      if (request === requestId) loading = false;
    }
  }

  async function applySelected(): Promise<void> {
    const instrument = activeInstrument;
    const preset = selected;
    if (!instrument || !preset || busy) return;
    busy = true;
    try {
      await instrument.applyPreset(preset.id);
      applyDialogOpen = false;
      toast.success(`Applied preset “${preset.name}”`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      busy = false;
    }
  }

  async function deleteSelected(): Promise<void> {
    const preset = selected;
    if (!preset || busy) return;
    const targetStationId = stationId;
    busy = true;
    try {
      await app.deletePreset(preset.instrument, preset.id);
      deleteDialogOpen = false;
      toast.success(`Deleted preset “${preset.name}”`);
      if (instrumentId === preset.instrument && presetId === preset.id && stationId === targetStationId) {
        await goto(
          resolve('/stations/[stationId]/instruments/[instrumentId]/presets', {
            stationId: targetStationId,
            instrumentId: preset.instrument
          })
        );
      }
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <div class="shrink-0 overflow-x-auto">
    <PageHeader items={breadcrumbItems} />
    {#if selected}
      <p class="px-4 pb-3 text-sm text-fg-muted">Created {dateFormat.format(new Date(selected.created_at))}</p>
    {/if}
  </div>

  <div class="min-h-0 flex-1 overflow-auto px-4 pb-4">
    {#if loading}
      <p class="py-8 text-center text-fg-muted" role="status">Loading preset…</p>
    {:else if loadError}
      <div class="flex flex-col items-center gap-3 py-8">
        <p class="text-fg-muted" role="alert">Unable to load preset: {loadError}</p>
        <Button variant="outline" size="xs" onclick={() => loadPreset()}>Retry</Button>
      </div>
    {:else if selected}
      <JsonView data={selected.value} expandDepth={1} />
    {:else}
      <p class="py-8 text-center text-fg-muted">Preset not found.</p>
    {/if}
  </div>

  {#if selected}
    <footer class="flex shrink-0 flex-wrap items-center gap-2 border-t border-line-muted px-4 py-3">
      <Button variant="ghost" size="sm" class="mr-auto" disabled={busy} onclick={() => (deleteDialogOpen = true)}>
        Delete…
      </Button>
      {#if !activeInstrument}
        <span class="text-sm text-fg-muted">Open the instrument to apply this preset.</span>
      {/if}
      <Button size="sm" disabled={!activeInstrument || busy} onclick={() => (applyDialogOpen = true)}>
        Apply preset
      </Button>
    </footer>
  {/if}
</div>

<Dialog.Root bind:open={applyDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Apply Preset</Dialog.Title>
      <Dialog.Description>
        Apply “{selected?.name}”? This replaces the current instrument configuration and planned tasks. Compatible
        specimen metadata is preserved.
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (applyDialogOpen = false)}>Cancel</Button>
      <Button loading={busy} disabled={!activeInstrument || !selected || busy} onclick={applySelected}
        >Apply Preset</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={deleteDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Delete Preset</Dialog.Title>
      <Dialog.Description>Delete “{selected?.name}”? This can't be undone.</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (deleteDialogOpen = false)}>Cancel</Button>
      <Button variant="danger" loading={busy} disabled={!selected || busy} onclick={deleteSelected}
        >Delete Preset</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
