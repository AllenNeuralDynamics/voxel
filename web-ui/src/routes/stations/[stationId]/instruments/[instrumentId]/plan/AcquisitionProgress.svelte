<script lang="ts">
  import { resolve } from '$app/paths';
  import { AlertCircleOutline, AlertOutline, Check, CircleDashed, DotsSpinner, Minus } from '$lib/icons';
  import {
    type AcquisitionManifest,
    type AcquisitionStatus,
    type AcquisitionVolume,
    getVoxelStation,
    type VolumeStatus
  } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { formatSpatialValue, getSpatialUnit } from '$lib/spatial-units';
  import { cn, displayName } from '$lib/utils';

  let { stationId, instrumentId }: { stationId: string; instrumentId: string } = $props();
  const app = getVoxelStation();
  const instrument = $derived(app.instrument?.id === instrumentId ? app.instrument : null);
  const progress = $derived(instrument?.acquisition ?? null);
  const manifest = $derived(
    progress
      ? (app.acquisitions.find((record) => record.id === progress.id && record.instrument === instrumentId) ?? null)
      : null
  );

  const dateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium'
  });

  const currentVolumeIndex = $derived(progress?.volume_index ?? -1);
  const currentVolume = $derived(manifest?.volumes[currentVolumeIndex] ?? null);
  const framesTotal = $derived(
    currentVolume ? Math.trunc((currentVolume.z_end - currentVolume.z_start) / currentVolume.z_step) + 1 : 0
  );
  const completedVolumes = $derived(manifest?.volumes.filter((volume) => volume.status === 'completed').length ?? 0);
  const framePercent = $derived(
    progress && framesTotal > 0 ? Math.min(100, Math.max(0, (progress.frames_captured / framesTotal) * 100)) : 0
  );
  const currentTaskPosition = $derived(currentVolume ? volumePosition(currentVolume) : null);

  function profileLabel(source: AcquisitionManifest, profileId: string): string {
    return source.state_snapshot.imaging.profiles[profileId]?.label || displayName(profileId);
  }

  function taskLabel(taskId: string): string {
    const index = manifest?.state_snapshot.plan.findIndex((task) => task.id === taskId) ?? -1;
    return index >= 0 ? `Task ${index + 1}` : 'Unknown task';
  }

  function volumePosition(volume: AcquisitionVolume): string {
    const unit = prefs.spatialUnit.get();
    return `X ${formatSpatialValue(volume.x, unit)} · Y ${formatSpatialValue(volume.y, unit)} · Z ${formatSpatialValue(volume.z_start, unit)}–${formatSpatialValue(volume.z_end, unit)} ${getSpatialUnit(unit).label}`;
  }

  function storageLabel(source: AcquisitionManifest): string {
    const { path, remote } = source.storage;
    if (!remote) return `Local · ${path}`;
    return `${remote.stage ? 'Staged' : 'Direct'} · ${remote.store} · ${remote.root}/${path}`;
  }

  function statusClass(status: AcquisitionStatus): string {
    if (status === 'failed') return 'border-danger/30 bg-danger/10 text-danger';
    if (status === 'interrupted') return 'border-warning/30 bg-warning/10 text-warning';
    return 'border-line-muted bg-element-bg text-fg-muted';
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

<section aria-labelledby="acquisition-progress-heading">
  <h2 id="acquisition-progress-heading" class="mb-2 text-base text-fg">Acquisition Progress</h2>
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

      <section class="overflow-hidden rounded-sm border border-line-muted bg-card/50">
        <div class="grid grid-cols-2 border-b border-line-faint">
          <div class="border-r border-line-faint px-3 py-2.5">
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

      {#if progress && currentVolume}
        <section class="mt-4 rounded-sm border border-line-muted bg-card/50 p-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm font-medium tracking-wide text-fg-muted uppercase">
                Current volume · {displayName(progress.phase)}
              </p>
              <h2 class="mt-1 truncate text-lg font-medium text-fg">
                {taskLabel(currentVolume.task)} · {profileLabel(manifest, currentVolume.profile)}
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
                {progress.frames_captured.toLocaleString()} / {framesTotal.toLocaleString()}
                <span class="ml-1 text-fg-muted">({Math.round(framePercent)}%)</span>
              </span>
            </div>
            <div
              class="h-2 overflow-hidden rounded-full bg-element-bg"
              role="progressbar"
              aria-label="Current volume frame progress"
              aria-valuemin="0"
              aria-valuemax={framesTotal}
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

        <div class="overflow-hidden rounded-sm border border-line-muted bg-card/50">
          {#each manifest.volumes as volume, index (index)}
            {@const current = index === currentVolumeIndex}
            <div
              class={cn(
                'grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 px-3 py-2.5',
                index > 0 && 'border-t border-line-faint',
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
                  {progress.frames_captured.toLocaleString()} / {framesTotal.toLocaleString()}
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
    <div class="rounded-sm border border-line-faint bg-element-bg/30 px-3 py-2 text-sm text-fg-muted" role="status">
      {progress ? 'Loading acquisition details…' : 'No acquisition running.'}
    </div>
  {/if}
</section>
