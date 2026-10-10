<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';

  import { resolve } from '$app/paths';
  import { AlertCircleOutline, AlertOutline, Check, Minus } from '$lib/icons';
  import { type AcquisitionManifest, getVoxelStation } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  let { stationId, instrumentId }: { stationId: string; instrumentId: string } = $props();
  const app = getVoxelStation();
  const activeId = $derived(app.instrument?.id === instrumentId ? app.instrument.acquisition?.id : undefined);
  const history = $derived(
    app.acquisitions
      .filter(
        (record) =>
          record.instrument === instrumentId &&
          record.id !== activeId &&
          record.status !== 'preparing' &&
          record.status !== 'running'
      )
      .toSorted((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
  );
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' });

  onMount(() => {
    void app.refresh();
  });
  watch(
    () => activeId,
    (current, previous) => {
      if (previous && !current) void app.refresh();
    }
  );

  function storageLabel(record: AcquisitionManifest): string {
    const { path, remote } = record.storage;
    if (!remote) return `Local · ${path}`;
    return `${remote.stage ? 'Staged' : 'Direct'} · ${remote.store} · ${remote.root}/${path}`;
  }
</script>

<section aria-labelledby="past-acquisitions-heading">
  <h2 id="past-acquisitions-heading" class="mb-2 text-base text-fg">Past Acquisitions</h2>
  {#if history.length}
    <div class="overflow-hidden rounded-md border border-line-muted">
      {#each history as record, index (record.id)}
        <a
          href={resolve('/stations/[stationId]/instruments/[instrumentId]/acquisitions/[acquisitionId]', {
            stationId,
            instrumentId,
            acquisitionId: record.id
          })}
          class={cn(
            'grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 px-3 py-3 transition-colors hover:bg-element-hover',
            index > 0 && 'border-t border-line-faint'
          )}
        >
          <span class="flex size-4 items-center justify-center" aria-label={displayName(record.status)}>
            {#if record.status === 'completed'}
              <Check class="size-3.5 text-fg-faint" aria-hidden="true" />
            {:else if record.status === 'failed'}
              <AlertCircleOutline class="size-3.5 text-danger" aria-hidden="true" />
            {:else if record.status === 'interrupted'}
              <AlertOutline class="size-3.5 text-warning" aria-hidden="true" />
            {:else}
              <Minus class="size-3.5 text-fg-faint" aria-hidden="true" />
            {/if}
          </span>
          <div class="min-w-0">
            <p class="truncate text-base text-fg">{dateFormat.format(new Date(record.created_at))}</p>
            <p class="mt-0.5 truncate text-sm text-fg-faint" title={storageLabel(record)}>{storageLabel(record)}</p>
          </div>
          <div class="text-right">
            <p class="text-sm text-fg-muted capitalize">{record.status}</p>
            <p class="mt-0.5 text-sm text-fg-faint tabular-nums">
              {record.volumes.length}
              {record.volumes.length === 1 ? 'volume' : 'volumes'}
            </p>
          </div>
        </a>
      {/each}
    </div>
  {:else}
    <p class="text-sm text-fg-muted">No past acquisitions recorded for this instrument.</p>
  {/if}
</section>
