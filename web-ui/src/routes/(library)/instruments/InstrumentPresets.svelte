<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { Button, Dialog, JsonView } from '$lib/kit';
  import { getVoxelApp, type Instrument, type PresetRecord } from '$lib/model';
  import PresetNameDialog from '$lib/PresetNameDialog.svelte';
  import { cn } from '$lib/utils';

  interface Props {
    instrumentName: string;
    presets: PresetRecord[];
    activeInstrument?: Instrument | null;
    onchanged: () => Promise<void>;
  }

  const { instrumentName, presets, activeInstrument = null, onchanged }: Props = $props();
  const app = getVoxelApp();

  let selectedId = $state<string | null>(null);
  let saveDialogOpen = $state(false);
  let applyDialogOpen = $state(false);
  let deleteDialogOpen = $state(false);
  let busy = $state(false);

  const selected = $derived(presets.find(({ id }) => id === selectedId) ?? presets[0] ?? null);
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

  watch(
    () => presets.map(({ id }) => id).join(','),
    () => {
      if (!presets.some(({ id }) => id === selectedId)) selectedId = presets[0]?.id ?? null;
    }
  );

  async function saveCurrent(name: string): Promise<void> {
    if (!activeInstrument) return;
    const created = await activeInstrument.savePreset(name);
    await onchanged();
    selectedId = created.id;
    toast.success(`Saved preset “${created.name}”`);
  }

  async function applySelected(): Promise<void> {
    if (!activeInstrument || !selected || busy) return;
    busy = true;
    try {
      await activeInstrument.applyPreset(selected.id);
      applyDialogOpen = false;
      toast.success(`Applied preset “${selected.name}”`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      busy = false;
    }
  }

  async function deleteSelected(): Promise<void> {
    if (!selected || busy) return;
    const deleted = selected;
    busy = true;
    try {
      await app.deletePreset(instrumentName, deleted.id);
      deleteDialogOpen = false;
      await onchanged();
      toast.success(`Deleted preset “${deleted.name}”`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex min-h-full gap-4 py-4">
  <aside class="w-64 shrink-0">
    <div class="mb-2 flex items-center justify-between gap-2">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">
        Presets{presets.length ? ` ${presets.length}` : ''}
      </h2>
      {#if activeInstrument}
        <Button variant="outline" size="xs" onclick={() => (saveDialogOpen = true)}>Save current…</Button>
      {/if}
    </div>

    {#if presets.length > 0}
      <div class="overflow-hidden rounded-lg border border-border bg-card">
        {#each presets as preset, index (preset.id)}
          <button
            type="button"
            class={cn(
              'block w-full px-3 py-2 text-left transition-colors hover:bg-element-hover',
              index > 0 && 'border-t border-border',
              selected?.id === preset.id && 'bg-element-active'
            )}
            onclick={() => (selectedId = preset.id)}
          >
            <span class="block truncate text-fg">{preset.name}</span>
            <span class="block text-sm text-fg-muted">{dateFormat.format(new Date(preset.created_at))}</span>
          </button>
        {/each}
      </div>
    {:else}
      <div class="rounded-lg border border-dashed border-border px-4 py-8 text-center text-fg-muted">
        No presets have been saved for this instrument.
      </div>
    {/if}
  </aside>

  <section class="min-w-0 flex-1">
    {#if selected}
      <div class="mb-2 flex items-center gap-2">
        <div class="min-w-0 flex-1">
          <h2 class="truncate text-lg font-medium text-fg">{selected.name}</h2>
          <p class="text-sm text-fg-muted">Created {dateFormat.format(new Date(selected.created_at))}</p>
        </div>
        <Button variant="ghost" size="xs" onclick={() => (deleteDialogOpen = true)}>Delete</Button>
        {#if activeInstrument}
          <Button size="xs" onclick={() => (applyDialogOpen = true)}>Apply</Button>
        {/if}
      </div>
      <JsonView data={selected.value} expandDepth={1} />
    {:else}
      <div class="flex h-full items-center justify-center text-fg-muted">Select a preset to inspect it.</div>
    {/if}
  </section>
</div>

<PresetNameDialog
  bind:open={saveDialogOpen}
  title="Save Current State as Preset"
  description="Save the current reusable configuration and acquisition tasks as a new preset."
  onsubmit={saveCurrent}
/>

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
      <Button loading={busy} onclick={applySelected}>Apply Preset</Button>
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
      <Button variant="danger" loading={busy} onclick={deleteSelected}>Delete Preset</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
