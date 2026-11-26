<script lang="ts">
  import type { Snippet } from 'svelte';

  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { Prefs } from '$lib/core/prefs';
  import {
    type Compression,
    type DownscaleType,
    SpimInstrument,
    SpimSession,
    type StorageSpec,
    type WriterSettings
  } from '$lib/core/spim.svelte';
  import type { MetadataField, MetadataSchema, SpecimenAxis } from '$lib/core/types';
  import { SPATIAL_UNITS } from '$lib/features/run/StageNumericField.svelte';
  import {
    Button,
    Checkbox,
    Collapsible,
    Dialog,
    Field,
    NumberBox,
    RadioList,
    Section,
    Select,
    TextBox
  } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { ChevronDown } from '@voxel/kit/icons';

  const AXES: SpecimenAxis[] = ['x', 'y', 'z'];
  const LOCAL = 'local';
  const COMPRESSIONS: Compression[] = ['blosc.lz4', 'blosc.zstd', 'zstd', 'lz4', 'gzip', 'none'];
  const DOWNSCALES: DownscaleType[] = ['gaussian', 'mean', 'min', 'max'];
  const LEVELS = [0, 1, 2, 3, 4, 5, 6, 7];
  const FACTS = 'grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 px-1.5 py-0.5';
  // From 48rem wide, the button moves to the right of the facts, at the bottom.
  const BODY = 'grid gap-2 @[48rem]/run-card:grid-cols-[minmax(0,1fr)_14rem] @[48rem]/run-card:gap-x-6';
  const LEFT = 'flex min-w-0 flex-col gap-2';

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const spim = $derived(selection.instrument instanceof SpimInstrument ? selection.instrument : undefined);
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const tasks = $derived(spim?.state.get('plan') ?? []);
  const writer = $derived(spim?.state.get('writer'));
  const acquisition = $derived(session?.acquisition);
  const unit = $derived(SPATIAL_UNITS[Prefs.spatialUnit.get()]);
  const stores = $derived(session?.remoteStores ?? {});

  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-');
  let path = $state('');
  let store = $state(LOCAL);
  let root = $state('');
  let stage = $state(false);
  let destinationOpen = $state(false);
  let formatOpen = $state(false);
  let starting = $state(false);
  // The metadata form: the station's forms by name, loaded when the dialog opens, and the one picked in it.
  let forms = $state<Record<string, { path: string; schema: MetadataSchema }>>({});
  let formOpen = $state(false);
  let formPick = $state('');
  const formPath = $derived(spim?.metadataForm ?? '');
  const nameOf = (path: string): string =>
    Object.entries(forms).find(([, form]) => form.path === path)?.[0] ?? path.split('.').at(-1) ?? '-';
  const formName = $derived(nameOf(formPath));

  // Each field that holds a value, as `group.field` inside a group, with its title and default.
  const leavesOf = (schema: MetadataSchema | undefined): Map<string, { title: string; default: unknown }> => {
    const found = new Map<string, { title: string; default: unknown }>();
    const resolve = (field: MetadataField): MetadataField =>
      field.$ref ? (schema?.$defs?.[field.$ref.split('/').at(-1) ?? ''] ?? field) : field;
    for (const [key, raw] of Object.entries(schema?.properties ?? {})) {
      const field = resolve(raw);
      if (!field.properties) found.set(key, { title: field.title ?? key, default: field.default });
      else
        for (const [inner, innerField] of Object.entries(field.properties))
          found.set(`${key}.${inner}`, {
            title: `${displayName(key)}, ${innerField.title ?? displayName(inner)}`,
            default: innerField.default
          });
    }
    return found;
  };
  // What the picked form changes: the fields it drops, with how many tasks hold a value in each, and those it adds.
  const formChange = $derived.by(() => {
    const now = leavesOf(session?.metadataSchema);
    const next = leavesOf(Object.values(forms).find((form) => form.path === formPick)?.schema);
    const valueAt = (metadata: Record<string, unknown>, path: string): unknown =>
      path.split('.').reduce<unknown>((at, key) => (at as Record<string, unknown> | undefined)?.[key], metadata);
    const filled = (value: unknown): boolean =>
      value !== undefined && value !== null && value !== '' && !(Array.isArray(value) && value.length === 0);
    return {
      dropped: [...now]
        .filter(([path]) => !next.has(path))
        .map(([path, field]): [string, string] => {
          const count = tasks.filter((task) => filled(valueAt(task.metadata, path))).length;
          return [field.title, count === 1 ? '1 task has a value' : `${count} tasks have a value`];
        }),
      added: [...next]
        .filter(([path]) => !now.has(path))
        .map(([, field]): [string, string] => [
          field.title,
          field.default === undefined ? '-' : JSON.stringify(field.default)
        ])
    };
  });
  $effect(() => {
    void station.metadataForms().then((found) => (forms = found), reportFailure);
  });

  function openForm(): void {
    formPick = formPath;
    formOpen = true;
  }

  async function changeForm(): Promise<void> {
    formOpen = false;
    if (formPick && formPick !== formPath) await reportFailure(session?.setMetadataForm(formPick));
  }

  const roots = $derived(stores[store]?.roots ?? {});
  const storage = $derived<StorageSpec>({
    path: path || `${name}/${stamp}`,
    remote: store === LOCAL ? null : { store, root: root || (Object.values(roots)[0] ?? ''), stage }
  });

  const run = $derived(station.lastRun);

  const volumes = $derived(session?.plannedVolumes.length ?? 0);
  const hasProblems = $derived((session?.startProblems(Prefs.operator.get()).length ?? 0) > 0);
  const ready = $derived(session !== undefined && !hasProblems && session.planFingerprint != null);

  /** The stage position of the visit that runs now: its stop on the tiled axes and its task's span on the scan axis. */
  const position = $derived.by(() => {
    const volume = acquisition ? session?.plannedVolumes[acquisition.visit] : undefined;
    const task = tasks.find((candidate) => candidate.id === volume?.task);
    const scan = spim?.config?.scan.axis;
    if (!volume || !task) return '-';
    const shown = (value: number) => (value / unit.scale).toFixed(unit.decimals);
    const parts = AXES.map((axis) =>
      axis === scan
        ? `${axis.toUpperCase()} ${shown(task.region.bounds[0])} to ${shown(task.region.bounds[1])}`
        : `${axis.toUpperCase()} ${shown(volume.at[axis] ?? 0)}`
    );
    return `${parts.join(', ')} ${unit.label}`;
  });

  function setWriter(fields: Partial<WriterSettings>): void {
    reportFailure(session?.updateWriterSettings(fields));
  }

  async function start(): Promise<void> {
    if (!session) return;
    starting = true;
    try {
      await session.startAcquisition(storage, Prefs.operator.get().trim(), session.planFingerprint);
    } catch (error) {
      reportFailure(error);
    } finally {
      starting = false;
    }
  }
</script>

{#snippet fold(label: string, value: string, open: boolean, toggle: (open: boolean) => void, body: Snippet)}
  <Collapsible.Root {open} onOpenChange={toggle}>
    <Collapsible.Trigger
      class="grid w-full cursor-pointer grid-cols-[6rem_minmax(0,1fr)_auto] items-center gap-x-3 rounded-sm px-1.5 py-0.5 text-left hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
    >
      <span class="text-fg-muted">{label}</span>
      <span class="truncate font-mono">{value}</span>
      <ChevronDown class={['size-3.5 text-fg-muted transition-transform', !open && '-rotate-90']} aria-hidden="true" />
    </Collapsible.Trigger>
    <Collapsible.Content>
      <div class="px-1.5 pt-2 pb-2">{@render body()}</div>
    </Collapsible.Content>
  </Collapsible.Root>
{/snippet}

{#snippet squares(states: string[])}
  <ol class="flex flex-wrap gap-0.75" aria-label="Volumes">
    {#each states as state, index (index)}
      <li class={['size-2.5 rounded-xs', state]}></li>
    {/each}
  </ol>
{/snippet}

{#snippet destination()}
  <div class="flex flex-col gap-3">
    <Field label="Store" id="run-store">
      <Select
        id="run-store"
        value={store}
        options={[LOCAL, ...Object.keys(stores)]}
        formatLabel={(option) => (option === LOCAL ? 'Local' : option)}
        onChange={(option) => {
          store = option;
          root = '';
        }}
      />
    </Field>
    {#if store !== LOCAL}
      <Field label="Root" id="run-root">
        <Select
          id="run-root"
          value={storage.remote?.root ?? ''}
          options={Object.values(roots)}
          formatLabel={(value) => Object.keys(roots).find((label) => roots[label] === value) ?? value}
          onChange={(value) => (root = value)}
        />
      </Field>
      <label class="flex items-center gap-2">
        <Checkbox value={stage} onChange={(value) => (stage = value)} aria-label="Stage upload" />Stage upload
      </label>
    {/if}
    <Field label="Path" id="run-path">
      <TextBox
        id="run-path"
        value={path}
        placeholder={`${name}/${stamp}`}
        onChange={(value) => (path = value.trim())}
      />
    </Field>
    <Field label="Operator" id="run-operator">
      <TextBox id="run-operator" value={Prefs.operator.get()} onChange={(value) => Prefs.operator.set(value.trim())} />
    </Field>
  </div>
{/snippet}

{#snippet format()}
  {#if writer}
    <div class="grid grid-cols-2 gap-3">
      <Field label="Compression" id="run-compression">
        <Select
          id="run-compression"
          value={writer.compression}
          options={COMPRESSIONS}
          disabled={!session}
          onChange={(compression) => setWriter({ compression })}
        />
      </Field>
      <Field label="Downscale" id="run-downscale">
        <Select
          id="run-downscale"
          value={writer.downscale_type}
          options={DOWNSCALES}
          disabled={!session}
          onChange={(downscale_type) => setWriter({ downscale_type })}
        />
      </Field>
      <Field label="Pyramid level" id="run-level">
        <Select
          id="run-level"
          value={writer.max_level}
          options={LEVELS}
          formatLabel={(level) => `L${level}`}
          disabled={!session}
          onChange={(max_level) => setWriter({ max_level })}
        />
      </Field>
      <Field label="Shard Z chunks" id="run-shard">
        <NumberBox
          id="run-shard"
          value={writer.shard_frame_chunks}
          min={1}
          step={1}
          decimals={0}
          disabled={!session}
          onChange={(shard_frame_chunks) => setWriter({ shard_frame_chunks })}
        />
      </Field>
      <Field label="Batch frames" id="run-batch">
        <NumberBox
          id="run-batch"
          value={writer.batch_frames}
          min={1}
          step={1}
          decimals={0}
          disabled={!session}
          onChange={(batch_frames) => setWriter({ batch_frames })}
        />
      </Field>
      <Field label="Target shard" id="run-target">
        <NumberBox
          id="run-target"
          value={writer.target_shard_gb}
          min={0}
          step={0.1}
          suffix="GB"
          disabled={!session}
          onChange={(target_shard_gb) => setWriter({ target_shard_gb })}
        />
      </Field>
    </div>
  {/if}
{/snippet}

<div class="@container/run-card">
  <Section heading="Run">
    {#snippet trailing()}
      {#if acquisition}
        <span class="text-sm text-accent-fg">Running</span>
      {:else}
        {#if ready}
          <span class="text-sm text-success-fg">Ready</span>
        {:else if hasProblems}
          <!-- The problems are in RunNotes, above the card or up the list of tasks. -->
          <button
            type="button"
            class="cursor-pointer rounded-sm text-sm text-danger-fg hover:underline focus-visible:outline-2 focus-visible:outline-focus"
            onclick={() =>
              document.getElementById('run-problems')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })}
          >
            Not ready
          </button>
        {:else}
          <span class="text-sm text-danger-fg">Not ready</span>
        {/if}
      {/if}
    {/snippet}

    <div class="frame-raised p-2.5">
      {#if acquisition}
        {@const volume = session?.plannedVolumes[acquisition.visit]}
        <div class={BODY}>
          <div class={LEFT}>
            {@render squares(
              Array.from({ length: acquisition.visits }, (_, i) =>
                i < acquisition.visit
                  ? 'bg-success-fg'
                  : i === acquisition.visit
                    ? 'bg-accent-fg'
                    : 'bg-element-selected'
              )
            )}
            <div class="-mx-1.5 flex flex-col gap-0.5 text-sm">
              <div class={FACTS}>
                <span class="text-fg-muted">Volume</span>
                <span class="tabular-nums"
                  >{Math.min(acquisition.visit + 1, acquisition.visits)} of {acquisition.visits}</span
                >
              </div>
              <div class={FACTS}>
                <span class="text-fg-muted">Task</span>
                <span class="truncate font-mono">{volume ? `${volume.task}, ${volume.profile}` : '-'}</span>
              </div>
              <div class={FACTS}>
                <span class="text-fg-muted">Position</span>
                <span class="truncate tabular-nums">{position}</span>
              </div>
              <div class={FACTS}>
                <span class="text-fg-muted">Time left</span>
                <span>-</span>
              </div>
              <div class={FACTS}>
                <span class="text-fg-muted">Writes to</span>
                <span class="truncate font-mono"
                  >{run?.id === acquisition.acquisition_id ? SpimSession.storageLabel(run.storage) : '-'}</span
                >
              </div>
            </div>
          </div>
          <Button
            variant="danger"
            class="w-full self-end"
            disabled={acquisition.stopping}
            onclick={() => reportFailure(session?.stopAcquisition())}
          >
            {acquisition.stopping ? 'Stopping…' : 'Stop run'}
          </Button>
        </div>
      {:else}
        <div class={BODY}>
          <div class={LEFT}>
            <div class="-mx-1.5 flex flex-col gap-0.5 text-sm">
              <div class={FACTS}>
                <span class="text-fg-muted">Total</span>
                <span class="grid grid-cols-3 gap-x-3 tabular-nums">
                  <span>{volumes} {volumes === 1 ? 'volume' : 'volumes'}</span>
                  <span>-</span>
                  <span>-</span>
                </span>
              </div>
              {@render fold(
                'Writes to',
                SpimSession.storageLabel(storage),
                destinationOpen,
                (open) => (destinationOpen = open),
                destination
              )}
              {@render fold(
                'Format',
                writer ? `${writer.compression}, pyramid L${writer.max_level}` : '-',
                formatOpen,
                (open) => (formatOpen = open),
                format
              )}
              <button
                type="button"
                class="grid w-full cursor-pointer grid-cols-[6rem_minmax(0,1fr)_auto] items-center gap-x-3 rounded-sm px-1.5 py-0.5 text-left hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-default disabled:opacity-50"
                disabled={!session}
                onclick={openForm}
              >
                <span class="text-fg-muted">Metadata</span>
                <span class="truncate">{formName}</span>
                <ChevronDown class="size-3.5 -rotate-90 text-fg-muted" aria-hidden="true" />
              </button>
            </div>
          </div>
          <Button class="w-full self-end" disabled={!ready || !session || starting} onclick={start}>Start run</Button>
        </div>
      {/if}
    </div>
  </Section>
</div>

<Dialog.Root bind:open={formOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Change metadata form</Dialog.Title>
    </Dialog.Header>
    <Field label="Form" id="metadata-form">
      {@const options = Object.values(forms).map((form) => form.path)}
      {#if options.length >= 2 && options.length <= 4}
        <RadioList
          id="metadata-form"
          value={formPick}
          {options}
          display={nameOf}
          onChange={(path) => (formPick = path)}
        />
      {:else}
        <Select
          id="metadata-form"
          value={formPick}
          {options}
          formatLabel={nameOf}
          onChange={(path) => (formPick = path)}
        />
      {/if}
    </Field>
    {#if formPick && formPick !== formPath}
      {#each [['Dropped', formChange.dropped] as const, ['Added', formChange.added] as const] as [heading, rows] (heading)}
        <div class="flex flex-col gap-1">
          <span class="text-sm text-fg-muted">{heading}</span>
          {#if rows.length > 0}
            <div class="frame-tinted">
              <table class="table-lined table-fixed [&_td:first-child]:w-[45%]">
                <tbody>
                  {#each rows as [title, detail] (title)}
                    <tr><td>{title}</td><td class="text-fg-muted">{detail}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <span class="text-sm text-fg-faint">None</span>
          {/if}
        </div>
      {/each}
    {/if}
    <Dialog.Footer>
      <Button size="lg" variant="ghost" onclick={() => (formOpen = false)}>Cancel</Button>
      <Button size="lg" disabled={!formPick || formPick === formPath} onclick={changeForm}>Change form</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
