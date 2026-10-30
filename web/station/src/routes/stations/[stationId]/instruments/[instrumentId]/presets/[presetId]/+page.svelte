<script lang="ts">
  import { resource, watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import { ApiError, type InstrumentDefaults, type PresetRecord } from '$lib/core/model';
  import { prefs, type StateView } from '$lib/core/prefs';
  import { cn, displayName, errorMessage } from '$lib/core/utils';
  import { Button, Dialog, JsonView, RadioBar, Section } from '$lib/kit';
  import { ChevronDown } from '$lib/kit/icons';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  type Confirm = 'apply' | 'update' | 'delete';

  interface Difference {
    path: string[];
    preset: unknown;
    now: unknown;
  }

  interface Change {
    key: string;
    label: string;
    unit: string;
    preset: unknown;
    now: unknown;
  }

  interface Group {
    key: string;
    title: string;
    changes: Change[];
  }

  const VIEWS: readonly StateView[] = ['changes', 'full'];
  const VIEW_LABELS: Record<StateView, string> = { changes: 'Changes', full: 'Full' };
  const ID_PARENTS = ['props', 'sync', 'setup', 'rois', 'waveforms'];
  const HIDDEN = ['props', 'sync'];
  const WORDS: Record<string, string> = {
    rois: 'ROI',
    waveforms: 'waveform',
    desc: 'description',
    z_step: 'Z step',
    metadata_cls: 'schema'
  };
  const UNITS: Record<string, string> = {
    mw: 'mW',
    ms: 'ms',
    us: 'µs',
    hz: 'Hz',
    percent: '%',
    um: 'µm',
    mm: 'mm',
    nm: 'nm',
    gb: 'GB'
  };
  const GRID = '@xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]';
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const routeParams = $derived(selected.params);
  const presetId = $derived(page.params.presetId ?? '');
  const isDefault = $derived(presetId === 'default');
  const instrument = $derived(selected.open);
  const saved = $derived(selected.saved);
  const current = $derived(instrument?.state ?? saved?.state ?? null);
  const loaded = resource(
    () => [routeParams.instrumentId, presetId] as const,
    async ([instrumentId, id], _, { signal }): Promise<PresetRecord | null> => {
      if (id === 'default') return null;
      try {
        const found = await app.fetchPreset(instrumentId, id);
        signal.throwIfAborted();
        return found;
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    }
  );
  const record = $derived(loaded.current?.id === presetId ? loaded.current : null);
  const loading = $derived(loaded.loading);
  const loadError = $derived(loaded.error ? errorMessage(loaded.error) : null);
  let pending = $state(false);
  let confirm = $state<Confirm>('apply');
  let confirmOpen = $state(false);
  const preset = $derived(
    isDefault ? (instrument?.default ?? saved?.config?.default ?? null) : (record?.value ?? null)
  );
  const name = $derived(isDefault ? 'Default' : (record?.name ?? (loading ? 'Loading…' : 'Preset')));
  const column = $derived(isDefault ? 'Default' : 'Preset');
  const tasks = $derived(isDefault ? 0 : (record?.value.plan.length ?? 0));
  const groups = $derived(preset && current ? groupChanges(divergence(settingsOf(preset), settingsOf(current))) : []);
  const total = $derived(groups.reduce((sum, group) => sum + group.changes.length, 0));
  const view = $derived(prefs.presets.view.get());
  const blocked = $derived.by((): string | null => {
    if (!instrument) return 'Open the instrument to change its settings.';
    if (instrument.busy) return 'Not possible while an acquisition runs.';
    if (!isDefault && instrument.activity.kind !== 'idle') return 'Stop the preview to apply.';
    return null;
  });
  const confirms = $derived<Record<Confirm, { title: string; text: string; action: string; danger: boolean }>>({
    apply: {
      title: `Apply ${name}?`,
      text: isDefault
        ? 'The current settings change to the default. The tasks and the sample values stay. You cannot undo this.'
        : `The current settings change to this preset. ${tasks ? `Its ${count(tasks, 'task')} replace the current tasks.` : 'It has no tasks, so the current tasks are removed.'} The sample values stay when their fields match. You cannot undo this.`,
      action: 'Apply',
      danger: false
    },
    update: {
      title: 'Update the default?',
      text: 'The default changes to the current settings. This writes config.yaml.',
      action: 'Update',
      danger: false
    },
    delete: {
      title: `Delete ${name}?`,
      text: 'Past runs keep their settings. You cannot undo this.',
      action: 'Delete',
      danger: true
    }
  });

  watch(
    () => [routeParams.instrumentId, presetId] as const,
    () => {
      confirmOpen = false;
    }
  );

  function ask(kind: Confirm): void {
    confirm = kind;
    confirmOpen = true;
  }

  async function confirmAction(): Promise<void> {
    confirmOpen = false;
    const target = instrument;
    const kind = confirm;
    const label = name;
    pending = true;
    try {
      if (kind === 'delete' && record) {
        await app.deletePreset(record.instrument, record.id);
        toast.success(`Deleted ${label}`);
        await goto(resolve('/stations/[stationId]/instruments/[instrumentId]/presets', routeParams));
      } else if (kind === 'update' && target) {
        await target.saveAsDefault();
        toast.success('Updated the default');
      } else if (kind === 'apply' && target) {
        if (isDefault) await target.restoreDefault();
        else if (record) await target.applyPreset(record.id);
        toast.success(`Applied ${label}`);
      }
    } catch (error) {
      reportFailure(error);
    } finally {
      pending = false;
    }
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

  function divergence(preset: unknown, now: unknown, path: string[] = []): Difference[] {
    if (isRecord(preset) && isRecord(now)) {
      const keys = new Set([...Object.keys(preset), ...Object.keys(now)]);
      return [...keys].flatMap((key) => divergence(preset[key], now[key], [...path, key]));
    }
    if (JSON.stringify(preset) === JSON.stringify(now)) return [];
    return [{ path, preset, now }];
  }

  function profileName(id: string): string {
    return (preset?.imaging.profiles[id] ?? current?.imaging.profiles[id])?.label || displayName(id);
  }

  function channelName(id: string): string {
    return (preset?.imaging.channels[id] ?? current?.imaging.channels[id])?.label || displayName(id);
  }

  function place(path: string[]): { key: string; title: string; lead: string; rest: string[] } {
    const [root, kind = '', id = '', ...rest] = path;
    if (root === 'imaging' && kind === 'profiles') {
      return { key: `profile:${id}`, title: `Profile ${profileName(id)}`, lead: '', rest };
    }
    if (root === 'imaging' && kind === 'channels') {
      return { key: 'channels', title: 'Channels', lead: channelName(id), rest };
    }
    if (root === 'routing') return { key: 'routing', title: 'Routing', lead: displayName(kind), rest: path.slice(2) };
    if (root === 'output') return { key: 'output', title: 'Output', lead: '', rest: path.slice(1) };
    return { key: 'sample', title: 'Sample fields', lead: '', rest: path };
  }

  function groupChanges(differences: Difference[]): Group[] {
    const byKey: Record<string, Group> = {};
    for (const { path, preset, now } of differences) {
      const { key, title, lead, rest } = place(path);
      const last = rest.at(-1) ?? '';
      const suffix = last.split('_').at(-1) ?? '';
      const unit = last.includes('_') ? (UNITS[suffix] ?? '') : '';
      const segments = unit ? [...rest.slice(0, -1), last.slice(0, -suffix.length - 1)] : rest;
      const words = segments.flatMap((segment, index) => {
        if (ID_PARENTS.includes(segments[index - 1] ?? '')) return [displayName(segment)];
        if (HIDDEN.includes(segment)) return [];
        return [WORDS[segment] ?? segment.replaceAll('_', ' ')];
      });
      const label = [lead, ...words].filter(Boolean).join(' ') || 'All settings';
      byKey[key] ??= { key, title, changes: [] };
      byKey[key].changes.push({
        key: path.join('.'),
        label: label.charAt(0).toUpperCase() + label.slice(1),
        unit,
        preset,
        now
      });
    }
    return Object.values(byKey);
  }

  function isText(value: unknown): boolean {
    if (Array.isArray(value)) return value.every((item) => typeof item !== 'object' || item === null);
    return typeof value !== 'object' || value === null;
  }

  function formatValue(value: unknown, unit: string): string {
    if (value === undefined) return 'Not set';
    if (value === null) return 'None';
    if (typeof value === 'number') return unit ? `${numberFormat.format(value)} ${unit}` : numberFormat.format(value);
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'string') return value === '' ? 'Empty' : value;
    if (Array.isArray(value)) return value.length ? value.join(', ') : 'None';
    return JSON.stringify(value);
  }
</script>

{#snippet valueCell(value: unknown, unit: string, tone: string)}
  {#if isText(value)}
    <span
      class={cn('line-clamp-3 wrap-anywhere', value === undefined ? 'text-fg-faint' : tone)}
      title={value === undefined ? undefined : String(value)}>{formatValue(value, unit)}</span
    >
  {:else}
    <div class="min-w-0"><JsonView data={value} expandDepth={1} /></div>
  {/if}
{/snippet}

<PageHeader
  items={[
    { label: 'Presets', href: resolve('/stations/[stationId]/instruments/[instrumentId]/presets', routeParams) },
    { label: name }
  ]}
>
  {#snippet trailing()}
    {#if record}
      <Button variant="ghost" disabled={pending} onclick={() => ask('delete')}>Delete…</Button>
    {/if}
  {/snippet}
</PageHeader>
<div class="page-body">
  {#if preset}
    <div class="flex min-w-0 flex-col gap-3">
      <div class="min-w-0 frame-raised p-2.5">
        <dl
          class="grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm [&>dd]:text-fg [&>dt]:text-fg-muted"
        >
          {#if record}
            <dt>Saved</dt>
            <dd>{dateFormat.format(new Date(record.created_at))}</dd>
          {:else}
            <dt>Kept in</dt>
            <dd class="font-mono">config.yaml</dd>
            <dt>Used when</dt>
            <dd><span class="font-mono">state.json</span> is missing</dd>
          {/if}
          <dt>Profiles</dt>
          <dd class="tabular-nums">{Object.keys(preset.imaging.profiles).length}</dd>
          <dt>Channels</dt>
          <dd class="tabular-nums">{Object.keys(preset.imaging.channels).length}</dd>
          {#if record}
            <dt>Tasks</dt>
            <dd class="tabular-nums">{tasks}</dd>
          {/if}
        </dl>
      </div>
      <Section heading="Compared with now" variant="raised" flush>
        {#snippet trailing()}
          <RadioBar
            value={view}
            options={VIEWS}
            formatLabel={(option) => VIEW_LABELS[option]}
            onChange={(option) => prefs.presets.view.set(option)}
            size="xs"
            aria-label="Comparison view"
          />
        {/snippet}
        {#if view === 'full'}
          <div class="overflow-x-auto p-2.5">
            <JsonView data={settingsOf(preset)} baseline={current ? settingsOf(current) : undefined} expandDepth={1} />
          </div>
        {:else if !current}
          <p class="px-2.5 py-2 text-sm text-fg-muted">The current settings are not available.</p>
        {:else if !groups.length}
          <p class="px-2.5 py-2 text-sm text-fg-muted">Matches now.</p>
        {:else}
          <div class="@container divide-y divide-line-faint">
            <div class={cn('hidden gap-x-3 px-2.5 py-1.5 text-xs text-fg-muted @xl:grid', GRID)}>
              <span>Setting</span>
              <span>{column}</span>
              <span>Now</span>
            </div>
            {#each groups as group (group.key)}
              <details class="group/changes min-w-0">
                <summary
                  class="flex h-9 cursor-pointer list-none items-center gap-2 px-2.5 group-open/changes:border-b group-open/changes:border-line-faint focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
                >
                  <h3 class="min-w-0 flex-1 truncate text-sm font-medium text-fg">{group.title}</h3>
                  <span class="shrink-0 text-sm text-fg-muted tabular-nums">
                    {count(group.changes.length, 'change')}
                  </span>
                  <ChevronDown
                    class="size-3.5 shrink-0 -rotate-90 text-fg-muted transition-transform group-open/changes:rotate-0"
                  />
                </summary>
                <ul class="divide-y divide-line-faint text-sm">
                  {#each group.changes as change (change.key)}
                    <li
                      class={cn(
                        'grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 px-2.5 py-1.5',
                        GRID
                      )}
                    >
                      <span class="col-span-full wrap-anywhere text-fg @xl:col-span-1" title={change.key}
                        >{change.label}</span
                      >
                      <span class="pl-3 text-fg-muted @xl:hidden">{column}</span>
                      {@render valueCell(change.preset, change.unit, 'text-fg-muted')}
                      <span class="pl-3 text-fg-muted @xl:hidden">Now</span>
                      {@render valueCell(change.now, change.unit, 'text-fg')}
                    </li>
                  {/each}
                </ul>
              </details>
            {/each}
          </div>
        {/if}
      </Section>
    </div>
  {:else if loading}
    <p class="py-8 text-center text-fg-muted" role="status">Loading the preset…</p>
  {:else if loadError}
    <div class="flex flex-col items-center gap-3 py-8">
      <p class="text-fg-muted" role="alert">Could not load the preset: {loadError}</p>
      <Button variant="outline" onclick={() => loaded.refetch()}>Retry</Button>
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This preset is not in the list.</p>
  {/if}
</div>
{#if preset}
  <footer class="shrink-0 border-t border-line-muted px-4 py-3">
    <div class="flex max-w-4xl flex-wrap items-center gap-2">
      <span class="text-sm text-fg-muted tabular-nums">
        {blocked ?? (total ? count(total, 'difference') : 'Matches now')}
      </span>
      <span class="ml-auto flex items-center gap-2">
        {#if isDefault}
          <Button variant="secondary" disabled={blocked !== null || pending || !total} onclick={() => ask('update')}>
            Update
          </Button>
        {/if}
        <Button disabled={blocked !== null || pending} onclick={() => ask('apply')}>Apply</Button>
      </span>
    </div>
  </footer>
{/if}

<Dialog.Root bind:open={confirmOpen}>
  <Dialog.Content size="md" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>{confirms[confirm].title}</Dialog.Title>
      <Dialog.Description>{confirms[confirm].text}</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button size="lg" variant="ghost" onclick={() => (confirmOpen = false)}>Cancel</Button>
      <Button
        size="lg"
        variant={confirms[confirm].danger ? 'danger' : 'default'}
        disabled={pending}
        onclick={confirmAction}
      >
        {confirms[confirm].action}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
