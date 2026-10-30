<script lang="ts">
  import { onMount } from 'svelte';

  import { resolve } from '$app/paths';
  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { type AcquisitionManifest, type AcquisitionStatus } from '$lib/core/model';
  import { RadioBar } from '$lib/kit';
  import { ArrowRight, Check, CircleAlert, DotsSpinner, Square, TriangleAlert } from '$lib/kit/icons';
  import { acquisitionHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  type Filter = 'all' | 'done' | 'failed' | 'stopped';

  const FILTERS: readonly Filter[] = ['all', 'done', 'failed', 'stopped'];
  const FILTER_LABELS: Record<Filter, string> = { all: 'All', done: 'Done', failed: 'Failed', stopped: 'Stopped' };
  // A run that the station lost, such as after a crash, counts as failed.
  const FILTER_STATUSES: Record<Exclude<Filter, 'all'>, readonly AcquisitionStatus[]> = {
    done: ['completed'],
    failed: ['failed', 'interrupted'],
    stopped: ['cancelled']
  };
  const STATUS: Record<AcquisitionStatus, { label: string; icon: typeof Check; color: string }> = {
    preparing: { label: 'Preparing', icon: DotsSpinner, color: 'text-fg-muted' },
    running: { label: 'Running', icon: DotsSpinner, color: 'text-fg-muted' },
    completed: { label: 'Done', icon: Check, color: 'text-fg-muted' },
    failed: { label: 'Failed', icon: CircleAlert, color: 'text-danger-fg' },
    cancelled: { label: 'Stopped', icon: Square, color: 'text-fg-muted' },
    interrupted: { label: 'Interrupted', icon: TriangleAlert, color: 'text-warning-fg' }
  };
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const routeParams = $derived(selected.params);
  const instrument = $derived(selected.open);
  // A run that goes now shows its progress on Run, so History lists only the runs that ended.
  const running = $derived(instrument?.activity.kind === 'capture');
  const records = $derived(
    app.acquisitions
      .filter(
        (manifest) =>
          manifest.instrument === routeParams.instrumentId &&
          manifest.status !== 'preparing' &&
          manifest.status !== 'running'
      )
      .toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
  );
  let filter = $state<Filter>('all');
  const shown = $derived.by(() => {
    if (filter === 'all') return records;
    const statuses = FILTER_STATUSES[filter];
    return records.filter((manifest) => statuses.includes(manifest.status));
  });

  onMount(() => {
    void app.refresh();
  });

  function finished(manifest: AcquisitionManifest): number {
    return manifest.volumes.filter((volume) => volume.status === 'completed').length;
  }

  function storagePath(manifest: AcquisitionManifest): string {
    const { path, remote } = manifest.storage;
    return remote ? `${remote.store} · ${remote.root}/${path}` : path;
  }
</script>

<PageHeader items={[{ label: 'History' }]}>
  {#snippet trailing()}
    <RadioBar
      value={filter}
      options={FILTERS}
      formatLabel={(option) => FILTER_LABELS[option]}
      onChange={(option) => (filter = option)}
      aria-label="Show acquisitions"
    />
  {/snippet}
</PageHeader>
<div class="page-body">
  <div class="flex min-w-0 flex-col gap-3">
    {#if running}
      <p class="flex flex-wrap items-center gap-x-2 frame-placeholder px-3 py-2 text-sm text-fg-muted">
        An acquisition is running. Its progress is on Run.
        <a
          href={resolve('/stations/[stationId]/instruments/[instrumentId]', routeParams)}
          class="inline-flex items-center gap-1 rounded-sm hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-focus"
          >Open Run<ArrowRight class="size-3" aria-hidden="true" /></a
        >
      </p>
    {/if}
    <div class="min-w-0 frame-raised p-1">
      {#if shown.length}
        <ul class="flex min-w-0 flex-col divide-y divide-line-faint">
          {#each shown as manifest (manifest.id)}
            {@const status = STATUS[manifest.status]}
            <li class="mx-2">
              <a
                href={acquisitionHref(routeParams, manifest.id)}
                class="-mx-2 flex min-w-0 items-start gap-2.5 rounded-md px-2 py-3 transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
              >
                <span role="img" aria-label={status.label} title={status.label} class="flex h-5 shrink-0 items-center">
                  <status.icon class="size-3.5 {status.color}" aria-hidden="true" />
                </span>
                <span class="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span class="flex min-w-0 items-center gap-2">
                    <span class="min-w-0 flex-1 truncate text-base font-medium text-fg"
                      >{dateFormat.format(new Date(manifest.created_at))}</span
                    >
                    <span class="shrink-0 text-sm text-fg-muted tabular-nums" title="Volumes finished"
                      >{finished(manifest)}/{manifest.volumes.length}</span
                    >
                  </span>
                  <span class="truncate font-mono text-sm text-fg-muted" title={storagePath(manifest)}
                    >{storagePath(manifest)}</span
                  >
                </span>
              </a>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="px-2 py-1.5 text-sm text-fg-muted">
          {records.length ? 'No acquisitions match this filter.' : 'No acquisitions recorded for this instrument.'}
        </p>
      {/if}
    </div>
  </div>
</div>
