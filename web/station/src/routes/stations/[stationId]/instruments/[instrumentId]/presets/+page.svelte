<script lang="ts">
  import { resource, watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { resolve } from '$app/paths';
  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import { type InstrumentDefaults, type PresetRecord } from '$lib/core/model';
  import { errorMessage } from '$lib/core/utils';
  import { Badge, Button, Dialog, Field, TextBox } from '$lib/kit';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  interface Row {
    id: string;
    name: string;
    detail: string;
    date?: string;
    settings: InstrumentDefaults;
  }

  const PRESET_ROUTE = '/stations/[stationId]/instruments/[instrumentId]/presets/[presetId]';
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const routeParams = $derived(selected.params);
  const instrument = $derived(selected.open);
  const saved = $derived(selected.saved);
  const current = $derived(instrument?.state ?? saved?.state ?? null);
  const defaults = $derived(instrument?.default ?? saved?.config?.default ?? null);
  const loaded = resource(
    () => routeParams.instrumentId,
    async (instrumentId, _, { signal }) => {
      if (!instrumentId) return [];
      const records = await app.fetchPresets(instrumentId);
      signal.throwIfAborted();
      return records;
    }
  );
  const presets = $derived((loaded.current ?? []).filter((preset) => preset.instrument === routeParams.instrumentId));
  const loading = $derived(loaded.loading);
  const loadError = $derived(loaded.error ? errorMessage(loaded.error) : null);
  let saveOpen = $state(false);
  let presetName = $state('');
  let saving = $state(false);
  const rows = $derived<Row[]>([
    ...(defaults ? [{ id: 'default', name: 'Default', detail: 'From config.yaml', settings: defaults }] : []),
    ...presets
      .toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
      .map((preset) => ({
        id: preset.id,
        name: preset.name,
        detail: summary(preset),
        date: dateFormat.format(new Date(preset.created_at)),
        settings: preset.value
      }))
  ]);

  watch(
    () => routeParams.instrumentId,
    () => {
      saveOpen = false;
    }
  );

  function openSave(): void {
    presetName = '';
    saveOpen = true;
  }

  async function saveCurrent(): Promise<void> {
    const name = presetName.trim();
    if (!name || saving) return;
    saving = true;
    try {
      if (!instrument) throw new Error('Open the instrument to save its settings.');
      const created = await instrument.savePreset(name);
      toast.success(`Saved ${created.name}`);
      await loaded.refetch();
      saveOpen = false;
    } catch (error) {
      reportFailure(error);
    } finally {
      saving = false;
    }
  }

  function summary(preset: PresetRecord): string {
    const { imaging, plan } = preset.value;
    const parts = [
      count(Object.keys(imaging.profiles).length, 'profile'),
      count(Object.keys(imaging.channels).length, 'channel')
    ];
    if (plan.length) parts.push(count(plan.length, 'task'));
    return parts.join(', ');
  }

  function count(value: number, noun: string): string {
    return `${value} ${noun}${value === 1 ? '' : 's'}`;
  }

  function settingsOf(source: InstrumentDefaults): InstrumentDefaults {
    return {
      imaging: source.imaging,
      routing: source.routing,
      metadata_cls: source.metadata_cls,
      output: source.output
    };
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function same(left: unknown, right: unknown): boolean {
    if (isRecord(left) && isRecord(right)) {
      const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
      return [...keys].every((key) => same(left[key], right[key]));
    }
    return JSON.stringify(left) === JSON.stringify(right);
  }
</script>

<PageHeader items={[{ label: 'Presets' }]}>
  {#snippet trailing()}
    {#if instrument}
      <Button variant="outline" onclick={openSave}>Save current…</Button>
    {/if}
  {/snippet}
</PageHeader>
<div class="page-body">
  {#if saved}
    <div class="min-w-0 frame-raised p-1">
      <ul class="flex min-w-0 flex-col divide-y divide-line-faint">
        {#each rows as row (row.id)}
          <li class="mx-2">
            <a
              href={resolve(PRESET_ROUTE, { ...routeParams, presetId: row.id })}
              class="-mx-2 flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-3 transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
            >
              <span class="flex min-w-0 items-center gap-2">
                <span class="min-w-0 truncate text-base font-medium text-fg">{row.name}</span>
                {#if current && same(settingsOf(row.settings), settingsOf(current))}
                  <Badge>Matches now</Badge>
                {/if}
                {#if row.date}
                  <span class="ml-auto shrink-0 text-sm text-fg-muted">{row.date}</span>
                {/if}
              </span>
              <span class="truncate text-sm text-fg-muted">{row.detail}</span>
            </a>
          </li>
        {/each}
      </ul>
      {#if loading}
        <p class="px-2 py-1.5 text-sm text-fg-muted" role="status">Loading presets…</p>
      {:else if loadError}
        <p class="flex flex-wrap items-center gap-2 px-2 py-1.5 text-sm text-fg-muted" role="alert">
          Could not load the presets: {loadError}
          <Button variant="outline" onclick={() => loaded.refetch()}>Retry</Button>
        </p>
      {:else if !presets.length}
        <p class="px-2 py-1.5 text-sm text-fg-muted">No presets saved yet.</p>
      {/if}
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This instrument is no longer in the catalog.</p>
  {/if}
</div>

<Dialog.Root bind:open={saveOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Save current settings</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-line-faint" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">Saves the current settings and tasks as a new preset.</p>
      <Field label="Preset Name" id="preset-name">
        <TextBox
          live
          size="lg"
          value={presetName}
          onChange={(text) => (presetName = text)}
          id="preset-name"
          placeholder="Preset name"
        />
      </Field>
    </div>

    <hr class="-mx-4 border-line-faint" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button size="lg" variant="outline" disabled={saving} onclick={() => (saveOpen = false)}>Cancel</Button>
      <Button size="lg" variant="success" disabled={!presetName.trim()} loading={saving} onclick={saveCurrent}
        >Save</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
