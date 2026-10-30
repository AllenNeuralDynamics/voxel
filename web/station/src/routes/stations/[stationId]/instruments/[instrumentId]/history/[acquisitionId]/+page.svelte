<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import {
    type AcquisitionManifest,
    type AcquisitionStatus,
    type AcquisitionVolume,
    type InstrumentDefaults,
    type InstrumentState,
    type VolumeStatus
  } from '$lib/core/model';
  import { cn, displayName } from '$lib/core/utils';
  import { Badge, CollapsibleSection, JsonView, Section } from '$lib/kit';
  import { Check, Copy } from '$lib/kit/icons';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  interface Difference {
    path: string[];
    run: unknown;
    now: unknown;
  }

  const STATUS_LABELS: Record<AcquisitionStatus, string> = {
    preparing: 'Preparing',
    running: 'Running',
    completed: 'Done',
    failed: 'Failed',
    cancelled: 'Stopped',
    interrupted: 'Interrupted'
  };
  const STATUS_TONES: Record<AcquisitionStatus, 'neutral' | 'success' | 'warning' | 'danger'> = {
    preparing: 'neutral',
    running: 'neutral',
    completed: 'success',
    failed: 'danger',
    cancelled: 'neutral',
    interrupted: 'warning'
  };
  const VOLUME_COLORS: Record<VolumeStatus, string> = {
    pending: 'bg-element-selected',
    running: 'bg-accent-fg',
    completed: 'bg-success-fg',
    failed: 'bg-danger-fg',
    cancelled: 'bg-fg-faint',
    skipped: 'bg-fg-faint'
  };
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' });

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const routeParams = $derived(selected.params);
  const manifest = $derived(
    app.acquisitions.find(
      (candidate) => candidate.id === page.params.acquisitionId && candidate.instrument === routeParams.instrumentId
    ) ?? null
  );
  const instrument = $derived(selected.open);
  const current = $derived(instrument?.state ?? selected.saved?.state ?? null);
  const differences = $derived(
    manifest && current ? divergence(settingsOf(manifest.state_snapshot), settingsOf(current)) : []
  );
  const finished = $derived(manifest?.volumes.filter((volume) => volume.status === 'completed').length ?? 0);
  const historyHref = $derived(resolve('/stations/[stationId]/instruments/[instrumentId]/history', routeParams));

  let copied = $state(false);
  let copiedTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    void app.refresh();
  });
  onDestroy(() => clearTimeout(copiedTimer));

  function settingsOf(state: InstrumentState | InstrumentDefaults): InstrumentDefaults {
    return { imaging: state.imaging, routing: state.routing, metadata_cls: state.metadata_cls, output: state.output };
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function divergence(run: unknown, now: unknown, path: string[] = []): Difference[] {
    if (isRecord(run) && isRecord(now)) {
      const keys = new Set([...Object.keys(run), ...Object.keys(now)]);
      return [...keys].flatMap((key) => divergence(run[key], now[key], [...path, key]));
    }
    if (JSON.stringify(run) === JSON.stringify(now)) return [];
    return [{ path, run, now }];
  }

  function formatValue(value: unknown): string {
    if (value === undefined) return '—';
    if (typeof value === 'string') return value === '' ? '""' : value;
    return JSON.stringify(value);
  }

  function storageLabel(source: AcquisitionManifest): string {
    const { path, remote } = source.storage;
    return remote ? `${remote.store} · ${remote.root}/${path}` : `Local · ${path}`;
  }

  function duration(source: AcquisitionManifest): string | null {
    if (!source.started_at || !source.ended_at) return null;
    const seconds = Math.max(0, Math.round((Date.parse(source.ended_at) - Date.parse(source.started_at)) / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours ? `${hours} h ${minutes} min` : minutes ? `${minutes} min ${seconds % 60} s` : `${seconds} s`;
  }

  function volumeTitle(source: AcquisitionManifest, volume: AcquisitionVolume, index: number): string {
    const task = source.state_snapshot.plan.findIndex((candidate) => candidate.id === volume.task) + 1;
    const profile = source.state_snapshot.imaging.profiles[volume.profile]?.label || displayName(volume.profile);
    return `Volume ${index + 1} · ${task ? `Task ${task}` : 'Unknown task'} · ${profile} · ${displayName(volume.status)}`;
  }

  function copyPath(source: AcquisitionManifest): void {
    void navigator.clipboard?.writeText(source.storage.path).then(
      () => {
        copied = true;
        clearTimeout(copiedTimer);
        copiedTimer = setTimeout(() => (copied = false), 1500);
      },
      () => reportFailure('Could not copy the path')
    );
  }
</script>

{#snippet valueCell(value: unknown, tone: string)}
  {#if typeof value === 'object' && value !== null}
    <div class="min-w-0"><JsonView data={value} expandDepth={1} /></div>
  {:else}
    <span
      class={cn('line-clamp-3 font-mono wrap-anywhere', value === undefined ? 'text-fg-faint' : tone)}
      title={formatValue(value)}>{formatValue(value)}</span
    >
  {/if}
{/snippet}

<PageHeader
  items={[
    { label: 'History', href: historyHref },
    { label: manifest ? dateFormat.format(new Date(manifest.created_at)) : 'Acquisition' }
  ]}
/>
<div class="page-body">
  {#if manifest}
    {@const runDuration = duration(manifest)}
    <div class="flex min-w-0 flex-col gap-3">
      <div class="min-w-0 frame-raised p-2.5">
        <dl class="grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
          <dt class="text-fg-muted">Status</dt>
          <dd class="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <Badge tone={STATUS_TONES[manifest.status]}>{STATUS_LABELS[manifest.status]}</Badge>
            {#if manifest.failure}
              <span class="min-w-0 text-danger-fg">{manifest.failure.kind}: {manifest.failure.message}</span>
            {/if}
          </dd>
          <dt class="text-fg-muted">Started</dt>
          <dd class="text-fg">{dateFormat.format(new Date(manifest.started_at ?? manifest.created_at))}</dd>
          {#if manifest.ended_at}
            <dt class="text-fg-muted">Ended</dt>
            <dd class="text-fg">
              {dateFormat.format(new Date(manifest.ended_at))}{#if runDuration}<span class="ml-2 text-fg-muted"
                  >{runDuration}</span
                >{/if}
            </dd>
          {/if}
          <dt class="text-fg-muted">Operator</dt>
          <dd class="text-fg">
            {manifest.origin.operator} <span class="text-fg-muted">on {manifest.origin.host}</span>
          </dd>
          <dt class="text-fg-muted">Destination</dt>
          <dd class="min-w-0 wrap-anywhere">
            <span class="font-mono text-fg">{storageLabel(manifest)}</span>
            {#if manifest.storage.remote?.stage}<span class="text-fg-muted">staged upload</span>{/if}
            <button
              type="button"
              class="inline-flex size-5 items-center justify-center rounded-sm align-middle text-fg-muted transition-colors hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
              title={copied ? 'Copied' : 'Copy path'}
              aria-label="Copy path"
              onclick={() => copyPath(manifest)}
            >
              {#if copied}
                <Check class="size-3.5" aria-hidden="true" />
              {:else}
                <Copy class="size-3.5" aria-hidden="true" />
              {/if}
            </button>
            <span class="sr-only" aria-live="polite">{copied ? 'Path copied' : ''}</span>
          </dd>
        </dl>
      </div>

      <Section heading="Volumes" variant="raised">
        {#snippet trailing()}
          <span class="text-sm text-fg-muted tabular-nums">{finished} of {manifest.volumes.length} finished</span>
        {/snippet}
        <div class="flex flex-wrap gap-0.75">
          {#each manifest.volumes as volume, index (index)}
            <span
              class={cn('size-2.5 rounded-xs', VOLUME_COLORS[volume.status])}
              title={volumeTitle(manifest, volume, index)}
            ></span>
          {/each}
        </div>
      </Section>

      <CollapsibleSection heading="Manifest">
        {#snippet trailing()}<span class="text-sm text-fg-muted">JSON</span>{/snippet}
        <div class="overflow-x-auto"><JsonView data={manifest} expandDepth={1} /></div>
      </CollapsibleSection>

      <CollapsibleSection heading="Settings used, compared with now" flush>
        {#snippet trailing()}
          <span class="text-sm text-fg-muted tabular-nums">
            {differences.length}
            {differences.length === 1 ? 'difference' : 'differences'}
          </span>
        {/snippet}
        {#if !current}
          <p class="px-2.5 py-2 text-sm text-fg-muted">The current settings are not available.</p>
        {:else if !differences.length}
          <p class="px-2.5 py-2 text-sm text-fg-muted">The current settings match this acquisition.</p>
        {:else}
          <div class="@container">
            <div class="grid grid-cols-1 text-sm @xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
              <div
                class="hidden grid-cols-subgrid gap-x-3 border-b border-line-faint px-2.5 py-1.5 text-xs text-fg-muted @xl:col-span-full @xl:grid"
              >
                <span>Key</span>
                <span>This run</span>
                <span>Now</span>
              </div>
              {#each differences as { path, run, now } (path.join('.'))}
                <div
                  class="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 px-2.5 py-1.5 not-last:border-b not-last:border-line-faint @xl:col-span-full @xl:grid-cols-subgrid"
                >
                  <span class="col-span-full wrap-anywhere text-fg @xl:col-span-1"
                    ><span class="text-fg-muted"
                      >{#each path.slice(0, -1) as key, index (index)}{key}.<wbr />{/each}</span
                    >{path.at(-1)}</span
                  >
                  <span class="pl-3 text-fg-muted @xl:hidden">This run</span>
                  {@render valueCell(run, 'text-fg-muted')}
                  <span class="pl-3 text-fg-muted @xl:hidden">Now</span>
                  {@render valueCell(now, 'text-fg')}
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </CollapsibleSection>
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This acquisition is not in the history.</p>
  {/if}
</div>
