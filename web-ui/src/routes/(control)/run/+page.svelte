<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { resolve } from '$app/paths';
  import { AlertCircleOutline, AlertOutline, Check, CircleDashed, DotsSpinner, Minus } from '$lib/icons';
  import { type AcquisitionManifest, type AcquisitionStatus, getVoxelApp, type VolumeStatus } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  const app = getVoxelApp();
  const acquisition = $derived(app.instrument?.acquisition ?? null);
  const manifest = $derived(acquisition?.manifest ?? null);
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
    progress ? Math.min(100, Math.max(0, (progress.frames_captured / progress.frames_total) * 100)) : 0
  );
  const currentTaskPosition = $derived(manifest && progress ? taskPosition(manifest, progress.task) : null);
  const recentAcquisitions = $derived(
    app.acquisitions
      .filter((candidate) => candidate.instrument === app.activeName)
      .toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
      .slice(0, 5)
  );

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
    return `X ${task.x.toLocaleString()} · Y ${task.y.toLocaleString()} · Z ${task.start.toLocaleString()}–${task.end.toLocaleString()} µm`;
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

<section class="flex h-full min-h-0 flex-col">
  {#if manifest && progress}
    <div class="min-h-0 flex-1 overflow-y-auto p-4">
      <header class="mb-4 flex min-w-0 items-start gap-3">
        <div class="min-w-0 flex-1">
          <h1 class="text-xl font-medium text-fg">Run</h1>
          <p class="mt-0.5 truncate font-mono text-sm text-fg-faint" title={manifest.id}>{manifest.id}</p>
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
              {#if current}
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
    <div class="min-h-0 flex-1 overflow-y-auto p-4">
      <header>
        <h1 class="text-xl font-medium text-fg">Run</h1>
        <p class="mt-1 text-base text-fg-muted">No acquisition currently running.</p>
      </header>

      <section class="mt-5">
        <div class="mb-2 flex items-baseline justify-between gap-3">
          <h2 class="text-sm font-medium tracking-wide text-fg-muted uppercase">Recent acquisitions</h2>
          {#if recentAcquisitions.length > 0}
            <span class="text-sm text-fg-faint">{displayName(app.activeName ?? '')}</span>
          {/if}
        </div>

        {#if recentAcquisitions.length > 0}
          <div class="overflow-hidden rounded-sm border border-border bg-card/50">
            {#each recentAcquisitions as recent, index (recent.id)}
              <a
                href={resolve(`/acquisitions/${recent.id}` as '/')}
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
            <p class="mt-3 text-base text-fg-muted">No acquisitions recorded for this instrument.</p>
            <a
              href={resolve('/plan')}
              class="mt-4 inline-flex h-ui-sm items-center rounded border border-border bg-element-bg px-3 text-base text-fg transition-colors hover:bg-element-hover"
            >
              Go to Plan
            </a>
          </div>
        {/if}
      </section>
    </div>
  {/if}
</section>
