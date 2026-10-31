<script lang="ts">
  import { watch } from 'runed';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { getPageInstrument, getRegionSelection, getVoxelStation } from '$lib/context.svelte';
  import {
    type AcquisitionManifest,
    type AcquisitionStatus,
    type AcquisitionTask,
    type Compression,
    createAreaTask,
    createPositionTask,
    deviceReady,
    type DownscaleType,
    type Instrument,
    isLoaded,
    type PlannedVolume,
    planningFov,
    type ScaleLevel,
    type VolumeStatus,
    type XYDefinition
  } from '$lib/core/model';
  import { planOverlap, prefs } from '$lib/core/prefs';
  import { formatSpatialValue, getSpatialUnit } from '$lib/core/spatial-units';
  import MetadataEditor from '$lib/features/run/MetadataEditor.svelte';
  import { acquisitionHref, deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { Badge, Button, Checkbox, CollapsibleSection, Field, Section, Select, SpinBox, TextBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { ArrowRight, Check, ChevronDown, CircleAlert, Plus, TriangleAlert } from '@voxel/kit/icons';
  import * as Sortable from '@voxel/kit/sortable';

  type CheckTone = 'ok' | 'warn' | 'block';

  interface ReadyCheck {
    tone: CheckTone;
    text: string;
    link?: { label: string; href: string };
    action?: { label: string; run: () => void };
  }

  const TASK_ROUTE = '/stations/[stationId]/instruments/[instrumentId]/(open)/run/[taskId]';
  const LOCAL_STORE = '__local__';
  const COMPRESSIONS: Compression[] = ['blosc.lz4', 'blosc.zstd', 'zstd', 'lz4', 'gzip', 'none'];
  const DOWNSCALE_TYPES: DownscaleType[] = ['gaussian', 'mean', 'min', 'max'];
  const PYRAMID_LEVELS: ScaleLevel[] = [0, 1, 2, 3, 4, 5, 6, 7];
  const TASK_TYPES: Record<XYDefinition['mode'], string> = {
    explicit_points: 'Positions',
    bounding_box: 'Area',
    convex_hull: 'Hull'
  };
  const STATUS: Record<
    AcquisitionStatus,
    { label: string; heading: string; tone: 'neutral' | 'success' | 'warning' | 'danger' }
  > = {
    preparing: { label: 'Preparing', heading: 'Acquisition preparing', tone: 'neutral' },
    running: { label: 'Running', heading: 'Acquisition running', tone: 'neutral' },
    completed: { label: 'Done', heading: 'Acquisition completed', tone: 'success' },
    failed: { label: 'Failed', heading: 'Acquisition failed', tone: 'danger' },
    cancelled: { label: 'Stopped', heading: 'Acquisition stopped', tone: 'neutral' },
    interrupted: { label: 'Interrupted', heading: 'Acquisition interrupted', tone: 'warning' }
  };
  const VOLUME_COLORS: Record<VolumeStatus, string> = {
    pending: 'bg-element-selected',
    running: 'bg-accent-fg',
    completed: 'bg-success-fg',
    failed: 'bg-danger-fg',
    cancelled: 'bg-fg-faint',
    skipped: 'bg-fg-faint'
  };
  const CHECK_ICONS: Record<CheckTone, typeof Check> = { ok: Check, warn: TriangleAlert, block: CircleAlert };
  const CHECK_COLORS: Record<CheckTone, string> = {
    ok: 'text-success-fg',
    warn: 'text-warning-fg',
    block: 'text-danger-fg'
  };
  const LINK =
    'inline-flex items-center gap-1 rounded-sm hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-focus';
  const DETAILS =
    'grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm text-fg [&>dt]:text-fg-muted';

  const app = getVoxelStation();
  const regionSelection = getRegionSelection();
  const selected = getPageInstrument();
  const instrumentId = $derived(selected.params.instrumentId);
  const routeParams = $derived(selected.params);
  const instrument = $derived(selected.open);
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));

  const saved = $derived(selected.saved);
  const savedState = $derived.by(() => {
    const info = app.discovery.instruments[instrumentId];
    return info && isLoaded(info.state) ? info.state.value : null;
  });
  const brokenFile = $derived(
    saved?.errorSource === 'config' ? 'config.yaml' : saved?.errorSource === 'state' ? 'state.json' : null
  );
  const opening = $derived(app.openingName === instrumentId || app.stationStatus === 'opening');
  const canOpen = $derived(
    app.stationStatus === 'idle' && app.openingName === null && !brokenFile && instrumentId in app.discovery.instruments
  );

  const tasks = $derived(instrument?.plan ?? savedState?.plan ?? []);
  const profiles = $derived(instrument?.imaging.profiles ?? savedState?.imaging.profiles ?? {});
  const locked = $derived(!instrument || instrument.busy || instrument.edits.pending);

  const preferenceKey = $derived(`${routeParams.stationId}/${routeParams.instrumentId}`);
  const currentPosition = $derived.by(() => {
    const x = instrument?.stage.x.position?.value;
    const y = instrument?.stage.y.position?.value;
    return x != null && y != null && Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  });
  const currentZRange = $derived.by(() => {
    const preferred = prefs.plan.defaults.get()[preferenceKey]?.zRange;
    if (preferred) return preferred;
    const z = instrument?.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });
  const currentProfile = $derived(
    instrument?.activeProfileId ?? Object.keys(instrument?.imaging.profiles ?? {})[0] ?? null
  );
  const currentFov = $derived(
    currentProfile && instrument ? planningFov(instrument.profileFovs, [currentProfile]) : null
  );
  const areaBounds = $derived.by(() => {
    const preferred = regionSelection.bounds ?? prefs.plan.defaults.get()[preferenceKey]?.region;
    if (preferred) return preferred;
    if (!currentPosition || !currentFov) return null;
    return {
      minX: currentPosition.x - currentFov[0] / 2,
      maxX: currentPosition.x + currentFov[0] / 2,
      minY: currentPosition.y - currentFov[1] / 2,
      maxY: currentPosition.y + currentFov[1] / 2
    };
  });
  const canAddPosition = $derived(!locked && !!currentPosition && !!currentZRange && !!currentProfile);
  const canAddArea = $derived(!locked && !!areaBounds && !!currentZRange && !!currentProfile && !!currentFov);

  const capture = $derived(instrument?.activity.kind === 'capture' ? instrument.activity : null);
  const active = $derived(capture?.acquisition ?? null);
  const manifest = $derived(active ? (app.acquisitions.find((record) => record.id === active.id) ?? null) : null);
  const volume = $derived(manifest && active ? (manifest.volumes[active.volume_index] ?? null) : null);
  const framesTotal = $derived(volume ? framesOf(volume) : 0);
  const percent = $derived.by(() => {
    if (!manifest?.volumes.length || !active) return 0;
    const current = framesTotal ? Math.min(1, active.frames_captured / framesTotal) : 0;
    return Math.round(((finished(manifest) + current) / manifest.volumes.length) * 100);
  });

  let lastRunId = $state<string | null>(null);
  const result = $derived(
    !capture && lastRunId ? (app.acquisitions.find((record) => record.id === lastRunId) ?? null) : null
  );
  watch(
    () => active?.id,
    (id) => {
      if (id) lastRunId = id;
    }
  );

  let store = $state(LOCAL_STORE);
  let root = $state('');
  let stage = $state(false);
  let path = $state(defaultPath());
  const remotes = $derived(instrument?.remoteStores ?? {});
  const roots = $derived<Record<string, string>>(store === LOCAL_STORE ? {} : (remotes[store]?.roots ?? {}));
  const destination = $derived(store === LOCAL_STORE ? path : `${store}:${root}/${path}`);

  let sampleOpen = $state(false);
  let destinationOpen = $state(false);
  let formatOpen = $state(false);
  let checksOpen = $state(true);

  const missing = $derived(
    instrument
      ? (instrument.metadataSchema?.required ?? []).filter((key) => isEmpty(instrument.state.metadata[key]))
      : []
  );
  const checks = $derived(instrument ? readyChecks(instrument) : []);
  const blockers = $derived(checks.filter((check) => check.tone === 'block').length);

  let starting = $state(false);

  function defaultPath(): string {
    const date = new Date();
    const pad = (value: number) => String(value).padStart(2, '0');
    const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
    return `${selected.params.instrumentId}/${stamp}`;
  }

  function pickStore(name: string): void {
    store = name;
    root = Object.values(name === LOCAL_STORE ? {} : (remotes[name]?.roots ?? {}))[0] ?? '';
  }

  function chunkEdge(level: ScaleLevel): number {
    return Math.max(64, 1 << level);
  }

  function framesOf(item: PlannedVolume): number {
    return Math.trunc((item.z_end - item.z_start) / item.z_step) + 1;
  }

  function finished(source: AcquisitionManifest): number {
    return source.volumes.filter((item) => item.status === 'completed').length;
  }

  function plural(count: number, word: string): string {
    return `${count} ${count === 1 ? word : `${word}s`}`;
  }

  function isEmpty(value: unknown): boolean {
    return value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length);
  }

  function taskVolumes(taskId: string): number {
    return instrument?.plannedVolumes.filter((item) => item.task === taskId).length ?? 0;
  }

  function profileLabels(task: AcquisitionTask): string {
    return task.profiles.map((id) => profiles[id]?.label || displayName(id)).join(', ') || 'No profile';
  }

  function readyChecks(source: Instrument): ReadyCheck[] {
    const out: ReadyCheck[] = [];
    out.push(
      source.plannedVolumes.length
        ? {
            tone: 'ok',
            text: `${plural(source.plan.length, 'task')} → ${plural(source.plannedVolumes.length, 'volume')}`
          }
        : { tone: 'block', text: 'No tasks planned' }
    );
    for (const device of source.devices.values()) {
      if (deviceReady(device)) continue;
      const href = deviceHref(routeParams, device.id);
      const reason = device.error || 'disconnected';
      out.push({ tone: 'block', text: `${displayName(device.id)}: ${reason}`, link: { label: 'Open device', href } });
    }
    out.push(
      missing.length
        ? {
            tone: 'block',
            text: `Sample: ${missing.map(displayName).join(', ')} is empty`,
            action: { label: 'Fill in', run: () => (sampleOpen = true) }
          }
        : { tone: 'ok', text: 'Sample info complete' }
    );
    if (source.activity.kind === 'preview') out.push({ tone: 'warn', text: 'Preview stops when the run starts.' });
    return out;
  }

  function estimateSeconds(source: Instrument): number {
    return source.plannedVolumes.reduce((total, item) => {
      const period = Math.max(
        0,
        ...Object.values(profiles[item.profile]?.sync ?? {}).map((signals) => signals.duration + signals.rest_time)
      );
      return total + framesOf(item) * period;
    }, 0);
  }

  function estimateGb(source: Instrument): number | null {
    const { channels } = source.state.imaging;
    let megabytes = 0;
    for (const item of source.plannedVolumes) {
      for (const channelId of profiles[item.profile]?.channels ?? []) {
        const frameMb = source.cameras.get(channels[channelId]?.detection ?? '')?.frameSizeMb?.value;
        if (typeof frameMb !== 'number') return null;
        megabytes += framesOf(item) * frameMb;
      }
    }
    return megabytes / 1000;
  }

  function formatDuration(seconds: number): string {
    const minutes = Math.round(seconds / 60);
    if (minutes < 1) return `${Math.max(1, Math.round(seconds))} s`;
    return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  }

  function formatGb(gb: number | null): string {
    if (gb === null) return '—';
    return gb >= 1000 ? `${(gb / 1000).toFixed(1)} TB` : gb >= 10 ? `${Math.round(gb)} GB` : `${gb.toFixed(1)} GB`;
  }

  function storageLabel(source: AcquisitionManifest): string {
    const { path: written, remote } = source.storage;
    return remote ? `${remote.store}:${remote.root}/${written}` : written;
  }

  function taskAndProfile(source: AcquisitionManifest, item: PlannedVolume): string {
    const task = source.state_snapshot.plan.findIndex((candidate) => candidate.id === item.task) + 1;
    const profile = source.state_snapshot.imaging.profiles[item.profile]?.label || displayName(item.profile);
    return `Task ${task}, ${profile}`;
  }

  function reorderTasks(ordered: AcquisitionTask[]): void {
    if (!instrument || locked) return;
    reportFailure(instrument.reorderTasks(ordered.map(({ id }) => id)));
  }

  async function addAtCurrentPosition(): Promise<void> {
    const target = instrument;
    if (!target || !currentPosition || !currentZRange || !currentProfile || locked) return;
    const z = currentZRange;
    const task = createPositionTask([currentPosition], currentProfile, z);
    await target.addTask(task);
    const defaults = prefs.plan.defaults.get();
    if (!defaults[preferenceKey]) {
      prefs.plan.defaults.set({ ...defaults, [preferenceKey]: { zRange: z, overlap: { x: 0.1, y: 0.1 } } });
    }
    if (instrument === target) await goto(resolve(TASK_ROUTE, { ...routeParams, taskId: task.id }));
  }

  async function addArea(): Promise<void> {
    const target = instrument;
    if (!target || !areaBounds || !currentZRange || !currentProfile || !currentFov || locked) return;
    const bounds = areaBounds;
    const z = currentZRange;
    const overlap = planOverlap(prefs.plan.defaults.get()[preferenceKey]?.overlap);
    const task = createAreaTask(bounds, overlap, currentProfile, z);
    await target.addTask(task);
    prefs.plan.defaults.set({
      ...prefs.plan.defaults.get(),
      [preferenceKey]: { region: { ...bounds }, zRange: z, overlap }
    });
    regionSelection.clear();
    if (instrument === target) await goto(resolve(TASK_ROUTE, { ...routeParams, taskId: task.id }));
  }

  async function start(source: Instrument): Promise<void> {
    starting = true;
    try {
      const record = await source.startAcquisition({
        storage: store === LOCAL_STORE ? { path } : { path, remote: { store, root, stage } },
        task_ids: null
      });
      lastRunId = record.id;
    } catch (error) {
      reportFailure(error);
    } finally {
      starting = false;
    }
  }

  function newRun(): void {
    lastRunId = null;
    path = defaultPath();
  }
</script>

{#snippet volumes(source: AcquisitionManifest)}
  <ol class="flex flex-wrap gap-0.75" aria-label="Volumes">
    {#each source.volumes as item, index (index)}
      <li
        class={cn('size-2.5 rounded-xs', VOLUME_COLORS[item.status])}
        title={`Volume ${index + 1}: ${taskAndProfile(source, item)}, ${displayName(item.status)}`}
      ></li>
    {/each}
  </ol>
{/snippet}

<PageHeader items={[{ label: 'Run' }]}>
  {#snippet trailing()}
    <Button variant="outline" disabled={!canAddPosition} onclick={() => reportFailure(addAtCurrentPosition())}>
      <Plus class="size-3.5" />
      Position
    </Button>
    <Button variant="outline" disabled={!canAddArea} onclick={() => reportFailure(addArea())}>
      <Plus class="size-3.5" />
      Area
    </Button>
  {/snippet}
</PageHeader>

<div class="page-body">
  <div class="flex min-w-0 flex-col gap-7">
    {#if !instrument}
      <p class="text-sm text-fg-muted">
        {#if brokenFile}
          This instrument cannot open. <code>{brokenFile}</code> has issues.
          <a href={resolve('/stations/[stationId]/instruments/[instrumentId]/config', routeParams)} class={LINK}
            >Open Config<ArrowRight class="size-3" aria-hidden="true" /></a
          >
        {:else if opening}
          <span role="status">Opening the instrument…</span>
        {:else}
          Tasks read only until it opens.
          {#if canOpen}
            <button
              type="button"
              class="ml-1 rounded-sm px-1 hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
              onclick={() => reportFailure(app.launch(instrumentId))}>Open instrument</button
            >
          {/if}
        {/if}
      </p>
    {/if}

    <Section heading="Tasks">
      {#if tasks.length}
        <Sortable.Root
          items={tasks}
          key={(task) => task.id}
          onReorder={reorderTasks}
          layout="vertical"
          class="flex flex-col gap-3 p-2"
          containerClass="-m-2"
        >
          {#snippet item(task: AcquisitionTask, index: number)}
            <Sortable.Item item={task} class="flex min-w-0 items-center frame-raised-link">
              <Sortable.Handle
                item={task}
                disabled={locked}
                class="mr-2 flex w-3 shrink-0 cursor-grab touch-none self-stretch overflow-hidden rounded-l-lg text-line-faint hover:bg-tint hover:text-fg-faint active:cursor-grabbing"
              >
                <span class="grip flex-1" aria-hidden="true"></span>
              </Sortable.Handle>
              <a
                href={resolve(TASK_ROUTE, { ...routeParams, taskId: task.id })}
                class="flex min-w-0 flex-1 flex-col gap-0.5 py-2 pr-2.5 focus-visible:outline-2 focus-visible:outline-focus"
              >
                <span class="flex min-w-0 items-center gap-2">
                  <span class="min-w-0 flex-1 truncate text-base text-fg">Task {index + 1}</span>
                  <Badge>{TASK_TYPES[task.xy.mode]}</Badge>
                  {#if instrument}
                    <span class="text-sm text-fg-muted tabular-nums">{plural(taskVolumes(task.id), 'volume')}</span>
                  {/if}
                </span>
                <span class="truncate text-sm text-fg-muted">{profileLabels(task)}</span>
              </a>
            </Sortable.Item>
          {/snippet}
        </Sortable.Root>
      {:else}
        <p class="px-2.5 text-sm text-fg-muted">No tasks.</p>
      {/if}
    </Section>

    {#if instrument}
      {@const output = instrument.state.output}
      <Section heading="Setup">
        <CollapsibleSection heading="Sample" bind:open={sampleOpen}>
          {#snippet trailing()}
            {#if missing.length}
              <span class="truncate text-sm text-danger-fg">{displayName(missing[0])} is empty</span>
            {/if}
          {/snippet}
          <fieldset class="min-w-0" disabled={Boolean(capture)}>
            <MetadataEditor {instrument} class="flex flex-col gap-3" />
          </fieldset>
        </CollapsibleSection>

        <CollapsibleSection heading="Destination" bind:open={destinationOpen}>
          {#snippet trailing()}
            <span class="truncate text-sm text-fg-muted">{store === LOCAL_STORE ? 'Local' : store}</span>
          {/snippet}
          <fieldset class="flex min-w-0 flex-col gap-3" disabled={Boolean(capture)}>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <Select
                prefix="Store"
                value={store}
                options={[LOCAL_STORE, ...Object.keys(remotes)]}
                formatLabel={(name) => (name === LOCAL_STORE ? 'Local' : name)}
                onChange={pickStore}
                class={store === LOCAL_STORE ? 'sm:col-span-3' : undefined}
              />
              {#if store !== LOCAL_STORE}
                <Select
                  prefix="Root"
                  value={root}
                  options={Object.values(roots)}
                  formatLabel={(name) => Object.keys(roots).find((label) => roots[label] === name) ?? name}
                  onChange={(name) => (root = name)}
                />
                <label
                  class="flex h-ui-sm items-center gap-2 text-base whitespace-nowrap text-fg"
                  title="Write to local scratch during the run, then upload to the destination"
                >
                  <Checkbox value={stage} onChange={(on) => (stage = on)} />
                  Stage upload
                </label>
              {/if}
            </div>
            <Field label="Path" id="run-path">
              <TextBox
                id="run-path"
                live
                value={path}
                placeholder="instrument/timestamp"
                onChange={(text) => (path = text)}
              />
            </Field>
          </fieldset>
        </CollapsibleSection>

        <CollapsibleSection heading="Format" bind:open={formatOpen}>
          {#snippet trailing()}
            <span class="truncate text-sm text-fg-muted">{output.compression}, pyramid L{output.max_level}</span>
          {/snippet}
          <fieldset class="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3" disabled={Boolean(capture)}>
            <Field label="Compression">
              <Select
                value={output.compression}
                options={COMPRESSIONS}
                onChange={(compression) => reportFailure(instrument.updateOutput({ compression }))}
              />
            </Field>
            <Field label="Downscale">
              <Select
                value={output.downscale_type}
                options={DOWNSCALE_TYPES}
                formatLabel={displayName}
                onChange={(value) => reportFailure(instrument.updateOutput({ downscale_type: value }))}
              />
            </Field>
            <Field label="Pyramid level">
              <Select
                value={output.max_level}
                options={PYRAMID_LEVELS}
                formatLabel={(level) => `L${level}`}
                onChange={(level) => reportFailure(instrument.updateOutput({ max_level: level }))}
              >
                {#snippet trailing(level)}
                  <span class="text-fg-muted tabular-nums">{chunkEdge(level)}³</span>
                {/snippet}
              </Select>
            </Field>
            <Field label="Shard Z chunks">
              <SpinBox
                value={output.shard_z_chunks}
                onChange={(value) => instrument.updateOutput({ shard_z_chunks: value })}
                onEditStart={() => instrument.edits.hold()}
                min={1}
                step={1}
                size="sm"
              />
            </Field>
            <Field label="Batch Z shards">
              <SpinBox
                value={output.batch_z_shards}
                onChange={(value) => instrument.updateOutput({ batch_z_shards: value })}
                onEditStart={() => instrument.edits.hold()}
                min={1}
                step={1}
                size="sm"
              />
            </Field>
            <Field label="Target shard">
              <SpinBox
                value={output.target_shard_gb}
                onChange={(value) => instrument.updateOutput({ target_shard_gb: value })}
                onEditStart={() => instrument.edits.hold()}
                min={0.1}
                step={0.05}
                bigStep={0.25}
                decimals={2}
                suffix="GB"
                size="sm"
              />
            </Field>
          </fieldset>
        </CollapsibleSection>
      </Section>
    {/if}
  </div>
</div>

<footer class="shrink-0 px-4 pt-4">
  <div class="max-w-4xl">
    {#if capture}
      <Section heading="Acquiring" variant="raised" class="frame-docked-bottom">
        {#snippet trailing()}
          {#if active}<Badge>{displayName(active.phase)}</Badge>{/if}
          <span class="text-sm text-fg-muted tabular-nums">{percent}%</span>
        {/snippet}
        <progress
          class="h-1.5 w-full appearance-none overflow-hidden rounded-full bg-element-bg [&::-moz-progress-bar]:bg-accent-fg [&::-webkit-progress-bar]:bg-element-bg [&::-webkit-progress-value]:bg-accent-fg"
          value={percent}
          max="100"
          aria-label="Acquisition progress"
        ></progress>
        {#if manifest && active && volume}
          <dl class={DETAILS}>
            <dt>Volume</dt>
            <dd>{active.volume_index + 1} of {manifest.volumes.length}</dd>
            <dt>Task</dt>
            <dd>{taskAndProfile(manifest, volume)}</dd>
            <dt>Frames</dt>
            <dd class="font-mono tabular-nums">{active.frames_captured} / {framesTotal}</dd>
            <dt>Position</dt>
            <dd class="font-mono tabular-nums">
              X {formatSpatialValue(volume.x, unit.value)}, Y {formatSpatialValue(volume.y, unit.value)}, Z
              {formatSpatialValue(volume.z_start, unit.value)} to {formatSpatialValue(volume.z_end, unit.value)}
              {unit.label}
            </dd>
            <dt>Writes to</dt>
            <dd class="font-mono wrap-anywhere">{storageLabel(manifest)}</dd>
          </dl>
          {@render volumes(manifest)}
        {:else}
          <p class="text-sm text-fg-muted" role="status">Preparing the acquisition…</p>
        {/if}
      </Section>
    {:else if result}
      <Section heading={STATUS[result.status].heading} variant="raised" class="frame-docked-bottom">
        {#snippet trailing()}
          <Badge tone={STATUS[result.status].tone}>{STATUS[result.status].label}</Badge>
        {/snippet}
        {#if result.failure}
          <p class="text-sm text-danger-fg">{result.failure.kind}: {result.failure.message}</p>
        {/if}
        <dl class={DETAILS}>
          <dt>Volumes</dt>
          <dd>{finished(result)} of {result.volumes.length} finished</dd>
          <dt>Writes to</dt>
          <dd class="font-mono wrap-anywhere">{storageLabel(result)}</dd>
        </dl>
        {@render volumes(result)}
        <a href={acquisitionHref(routeParams, result.id)} class={cn(LINK, 'self-start text-sm text-fg-muted')}
          >Open in History<ArrowRight class="size-3" aria-hidden="true" /></a
        >
        <Button class="w-full" onclick={newRun}>New run</Button>
      </Section>
    {:else}
      <Section heading="Ready to acquire?" variant="raised" class="frame-docked-bottom">
        {#snippet trailing()}
          {#if instrument}
            <button
              type="button"
              class={cn(
                'flex items-center gap-1 rounded-sm px-1.5 text-sm/5  focus-visible:outline-2 focus-visible:outline-focus',
                blockers ? 'bg-danger-tint text-danger-fg' : 'bg-success-tint text-success-fg'
              )}
              aria-expanded={checksOpen}
              title={checksOpen ? 'Hide the checks' : 'Show the checks'}
              onclick={() => (checksOpen = !checksOpen)}
            >
              {blockers ? plural(blockers, 'issue') : 'Ready'}
              <ChevronDown class={cn('size-3 transition-transform', checksOpen && 'rotate-180')} />
            </button>
          {:else}
            <Badge>Closed</Badge>
          {/if}
        {/snippet}
        {#if instrument}
          {#if checksOpen}
            <ul class="flex flex-col gap-1 border-b border-line-faint pb-2 text-sm">
              {#each checks as check, index (index)}
                {@const Icon = CHECK_ICONS[check.tone]}
                <li class={cn('flex min-w-0 items-center gap-2', check.tone === 'block' ? 'text-fg' : 'text-fg-muted')}>
                  <Icon class={cn('size-3.5 shrink-0', CHECK_COLORS[check.tone])} aria-hidden="true" />
                  {check.text}
                  {#if check.link}
                    <a href={check.link.href} class={cn(LINK, 'ml-auto shrink-0 text-fg-muted')}
                      >{check.link.label}<ArrowRight class="size-3" aria-hidden="true" /></a
                    >
                  {:else if check.action}
                    <button
                      type="button"
                      class="ml-auto shrink-0 rounded-sm text-fg-muted hover:text-fg hover:underline"
                      onclick={check.action.run}>{check.action.label}</button
                    >
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
          <dl class={DETAILS}>
            <dt>Volumes</dt>
            <dd>{instrument.plannedVolumes.length}</dd>
            <dt>Time</dt>
            <dd>{formatDuration(estimateSeconds(instrument))}</dd>
            <dt>Data</dt>
            <dd>{formatGb(estimateGb(instrument))}</dd>
            <dt>Writes to</dt>
            <dd class="font-mono wrap-anywhere">{destination}</dd>
          </dl>
        {:else}
          <p class="text-sm text-fg-muted">Starts once the instrument opens.</p>
        {/if}
        <Button
          class="w-full"
          disabled={!instrument || blockers > 0 || starting}
          onclick={() => instrument && start(instrument)}
        >
          {starting ? 'Starting…' : 'Start acquisition'}
        </Button>
      </Section>
    {/if}
  </div>
</footer>

<style>
  /* Tiny dots in the text color, like the knurled grip on a knob. The task handle uses them. */
  .grip {
    background-image: radial-gradient(circle, currentColor 0.5px, transparent 0.6px);
    background-size: 2px 2px;
  }
</style>
