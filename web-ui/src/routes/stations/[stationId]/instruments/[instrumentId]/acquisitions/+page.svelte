<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';

  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { AlertCircleOutline, AlertOutline, Check, CircleDashed, DotsSpinner, Minus } from '$lib/icons';
  import { type AcquisitionManifest, type AcquisitionStatus, getVoxelStation, type VolumeStatus } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { formatSpatialValue, getSpatialUnit } from '$lib/spatial-units';
  import { cn, displayName } from '$lib/utils';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const routeParams = $derived({ stationId, instrumentId });
  const instrument = $derived(app.instrument?.id === instrumentId ? app.instrument : null);
  const acquisition = $derived(instrument?.acquisition ?? null);
  let lastManifest = $state.raw<AcquisitionManifest | null>(null);
  const acquisitions = $derived.by(() => {
    const records = app.acquisitions.filter((candidate) => candidate.instrument === instrumentId);
    const observed = acquisition?.manifest ?? lastManifest;
    if (observed && observed.instrument === instrumentId) {
      const index = records.findIndex((candidate) => candidate.id === observed.id);
      if (index < 0) records.push(observed);
      else if (records[index].revision < observed.revision) records[index] = observed;
    }
    return records.toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
  });
  const manifest = $derived(acquisition?.manifest ?? null);

  onMount(() => {
    void app.refresh();
  });

  watch(
    () => acquisition,
    (current, previous) => {
      if (current) lastManifest = current.manifest;
      else if (previous) void app.refresh();
    }
  );
  const progress = $derived(acquisition?.progress ?? null);

  const dateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium'
  });

  const taskOrdinals = $derived.by(() => {
    const ordinals = new SvelteMap<string, number>();
    for (const volume of manifest?.volumes ?? []) {
      if (!ordinals.has(volume.task)) ordinals.set(volume.task, ordinals.size + 1);
    }
    return ordinals;
  });

  const currentVolumeIndex = $derived(
    manifest && progress
      ? manifest.volumes.findIndex((volume) => volume.task === progress.task && volume.profile === progress.profile)
      : -1
  );
  const completedVolumes = $derived(manifest?.volumes.filter((volume) => volume.status === 'completed').length ?? 0);
  const framePercent = $derived(
    progress && progress.frames_total > 0
      ? Math.min(100, Math.max(0, (progress.frames_captured / progress.frames_total) * 100))
      : 0
  );
  const currentTaskPosition = $derived(manifest && progress ? taskPosition(manifest, progress.task) : null);
  const history = $derived(acquisitions.filter((candidate) => candidate.id !== manifest?.id));

  function profileLabel(source: AcquisitionManifest, profileId: string): string {
    return source.state_snapshot.imaging.profiles[profileId]?.label || displayName(profileId);
  }

  function taskLabel(taskId: string): string {
    const ordinal = taskOrdinals.get(taskId);
    return ordinal ? `Task ${String(ordinal).padStart(4, '0')}` : 'Unknown task';
  }

  function taskPosition(source: AcquisitionManifest, taskId: string): string | null {
    const task = source.state_snapshot.tasks[taskId];
    if (!task) return null;
    const unit = prefs.spatialUnit.get();
    return `X ${formatSpatialValue(task.x, unit)} · Y ${formatSpatialValue(task.y, unit)} · Z ${formatSpatialValue(task.start, unit)}–${formatSpatialValue(task.end, unit)} ${getSpatialUnit(unit).label}`;
  }

  function storageLabel(source: AcquisitionManifest): string {
    const { path, remote } = source.storage;
    if (!remote) return `Local · ${path}`;
    return `${remote.stage ? 'Staged' : 'Direct'} · ${remote.store} · ${remote.root}/${path}`;
  }

  function statusClass(status: AcquisitionStatus): string {
    if (status === 'failed') return 'border-danger/30 bg-danger/10 text-danger';
    if (status === 'interrupted') return 'border-warning/30 bg-warning/10 text-warning';
    return 'border-border bg-element-bg text-fg-muted';
  }
</script>

{#snippet statusIcon(status: AcquisitionStatus | VolumeStatus, size = 14)}
  <span class="flex size-4 shrink-0 items-center justify-center" aria-label={displayName(status)}>
    {#if status === 'completed'}
      <Check width={size} height={size} class="text-fg-faint" aria-hidden="true" />
    {:else if status === 'running'}
      <span class="size-1.5 animate-pulse rounded-full bg-info" aria-hidden="true"></span>
    {:else if status === 'preparing'}
      <DotsSpinner width={size} height={size} class="text-info" aria-hidden="true" />
    {:else if status === 'failed'}
      <AlertCircleOutline width={size} height={size} class="text-danger" aria-hidden="true" />
    {:else if status === 'interrupted'}
      <AlertOutline width={size} height={size} class="text-warning" aria-hidden="true" />
    {:else if status === 'pending'}
      <CircleDashed width={size} height={size} class="text-fg-faint" aria-hidden="true" />
    {:else}
      <Minus width={size} height={size} class="text-fg-faint" aria-hidden="true" />
    {/if}
  </span>
{/snippet}

<section class="flex min-h-full flex-col gap-5 px-4 pb-4">
  <section aria-labelledby="current-acquisition-heading">
    <h2 id="current-acquisition-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-muted uppercase">
      Current acquisition
    </h2>
    {#if manifest}
      <div>
        <header class="mb-4 flex min-w-0 items-start gap-3">
          <div class="min-w-0 flex-1">
            <a
              href={resolve('/stations/[stationId]/instruments/[instrumentId]/acquisitions/[acquisitionId]', {
                stationId,
                instrumentId: manifest.instrument,
                acquisitionId: manifest.id
              })}
              class="block truncate font-mono text-sm text-fg-faint hover:text-fg hover:underline"
              title="View acquisition details"
            >
              {manifest.id}
            </a>
          </div>
          <span
            class={cn(
              'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-1 text-sm capitalize',
              statusClass(manifest.status)
            )}
          >
            {@render statusIcon(manifest.status, 13)}
            {manifest.status}
          </span>
        </header>

        {#if manifest.failure}
          <div class="mb-4 flex gap-2 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-danger">
            <AlertCircleOutline width="16" height="16" class="mt-0.5 shrink-0" />
            <div class="min-w-0">
              <p class="font-medium">{displayName(manifest.failure.kind)}</p>
              <p class="mt-0.5 text-sm wrap-break-word">{manifest.failure.message}</p>
            </div>
          </div>
        {/if}

        <section class="overflow-hidden rounded-sm border border-border bg-card/50">
          <div class="grid grid-cols-2 border-b border-border">
            <div class="border-r border-border px-3 py-2.5">
              <p class="text-sm text-fg-faint">Started</p>
              <p class="mt-0.5 truncate text-base text-fg">
                {manifest.started_at ? dateFormat.format(new Date(manifest.started_at)) : 'Preparing'}
              </p>
            </div>
            <div class="px-3 py-2.5">
              <p class="text-sm text-fg-faint">Operator</p>
              <p
                class="mt-0.5 truncate text-base text-fg"
                title={`${manifest.origin.operator} on ${manifest.origin.host}`}
              >
                {manifest.origin.operator}
                <span class="text-fg-muted">on {manifest.origin.host}</span>
              </p>
            </div>
          </div>
          <div class="px-3 py-2.5">
            <p class="text-sm text-fg-faint">Destination</p>
            <p class="mt-0.5 truncate text-base text-fg" title={storageLabel(manifest)}>{storageLabel(manifest)}</p>
          </div>
        </section>

        {#if progress}
          <section class="mt-4 rounded-sm border border-border bg-card/50 p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-sm font-medium tracking-wide text-fg-muted uppercase">Current volume</p>
                <h2 class="mt-1 truncate text-lg font-medium text-fg">
                  {taskLabel(progress.task)} · {profileLabel(manifest, progress.profile)}
                </h2>
                {#if currentTaskPosition}
                  <p class="mt-0.5 truncate text-sm text-fg-muted" title={currentTaskPosition}>
                    {currentTaskPosition}
                  </p>
                {/if}
              </div>
              <span class="shrink-0 text-sm text-fg-muted tabular-nums">
                Volume {Math.max(currentVolumeIndex + 1, 1)} of {manifest.volumes.length}
              </span>
            </div>

            <div class="mt-4">
              <div class="mb-1.5 flex items-baseline justify-between gap-3 text-sm tabular-nums">
                <span class="text-fg-muted">Frames</span>
                <span class="text-fg">
                  {progress.frames_captured.toLocaleString()} / {progress.frames_total.toLocaleString()}
                  <span class="ml-1 text-fg-muted">({Math.round(framePercent)}%)</span>
                </span>
              </div>
              <div
                class="h-2 overflow-hidden rounded-full bg-element-bg"
                role="progressbar"
                aria-label="Current volume frame progress"
                aria-valuemin="0"
                aria-valuemax={progress.frames_total}
                aria-valuenow={progress.frames_captured}
              >
                <div
                  class="h-full rounded-full bg-info transition-[width] duration-200"
                  style={`width: ${framePercent}%`}
                ></div>
              </div>
            </div>
          </section>
        {/if}

        <section class="mt-5">
          <div class="mb-2 flex items-baseline justify-between gap-3">
            <h2 class="text-sm font-medium tracking-wide text-fg-muted uppercase">Volumes</h2>
            <span class="text-sm text-fg-faint tabular-nums">
              {completedVolumes} of {manifest.volumes.length} completed
            </span>
          </div>

          <div class="overflow-hidden rounded-sm border border-border bg-card/50">
            {#each manifest.volumes as volume, index (`${volume.task}:${volume.profile}`)}
              {@const current = index === currentVolumeIndex}
              <div
                class={cn(
                  'grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 px-3 py-2.5',
                  index > 0 && 'border-t border-border',
                  current && 'bg-element-selected/40'
                )}
              >
                {@render statusIcon(volume.status)}
                <div class="min-w-0">
                  <p class="truncate text-base text-fg">
                    {taskLabel(volume.task)}
                    <span class="text-fg-muted">· {profileLabel(manifest, volume.profile)}</span>
                  </p>
                </div>
                {#if current && progress}
                  <span class="text-sm text-fg-muted tabular-nums">
                    {progress.frames_captured.toLocaleString()} / {progress.frames_total.toLocaleString()}
                  </span>
                {:else}
                  <span class="text-sm text-fg-faint capitalize">{volume.status}</span>
                {/if}
              </div>
            {/each}
          </div>
        </section>
      </div>
    {:else}
      <div
        class="rounded-sm border border-border-faint/50 bg-element-bg/30 px-3 py-2 text-sm text-fg-muted"
        role="status"
      >
        No acquisition running.
      </div>
    {/if}
  </section>

  <section>
    <div class="mb-2 flex items-baseline justify-between gap-3">
      <h2 class="text-sm font-medium tracking-wide text-fg-muted uppercase">History</h2>
      {#if history.length > 0}
        <span class="text-sm text-fg-faint">{displayName(instrumentId ?? '')}</span>
      {/if}
    </div>

    {#if history.length > 0}
      <div class="overflow-hidden rounded-sm border border-border bg-card/50">
        {#each history as recent, index (recent.id)}
          <a
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/acquisitions/[acquisitionId]', {
              stationId,
              instrumentId: recent.instrument,
              acquisitionId: recent.id
            })}
            class={cn(
              'grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 px-3 py-3 transition-colors hover:bg-element-hover',
              index > 0 && 'border-t border-border'
            )}
          >
            {@render statusIcon(recent.status)}
            <div class="min-w-0">
              <p class="truncate text-base text-fg">{dateFormat.format(new Date(recent.created_at))}</p>
              <p class="mt-0.5 truncate text-sm text-fg-faint" title={storageLabel(recent)}>
                {storageLabel(recent)}
              </p>
            </div>
            <div class="text-right">
              <p class="text-sm text-fg-muted capitalize">{recent.status}</p>
              <p class="mt-0.5 text-sm text-fg-faint tabular-nums">
                {recent.volumes.length}
                {recent.volumes.length === 1 ? 'volume' : 'volumes'}
              </p>
            </div>
          </a>
        {/each}
      </div>
    {:else}
      <div class="rounded-sm border border-dashed border-border px-5 py-10 text-center">
        <CircleDashed width="26" height="26" class="mx-auto text-fg-faint" />
        <p class="mt-3 text-base text-fg-muted">
          {manifest
            ? 'No earlier acquisitions recorded for this instrument.'
            : 'No acquisitions recorded for this instrument.'}
        </p>
        {#if instrument}
          <a
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/plan', routeParams)}
            class="mt-4 inline-flex h-ui-sm items-center rounded border border-border bg-element-bg px-3 text-base text-fg transition-colors hover:bg-element-hover"
          >
            Go to Plan
          </a>
        {/if}
      </div>
    {/if}
  </section>
</section>
