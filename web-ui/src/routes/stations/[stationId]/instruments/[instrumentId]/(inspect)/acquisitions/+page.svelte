<script lang="ts">
  import { page } from '$app/state';
  import { AlertCircleOutline, AlertOutline, Check, DotsSpinner, Minus, Record } from '$lib/icons';
  import { type AcquisitionManifest, getVoxelStation } from '$lib/model';
  import { cn } from '$lib/utils';

  import { instrumentAcquisitionPath } from '../../../sections';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId);
  const id = $derived(page.params.instrumentId);
  const acquisitions = $derived(id ? app.acquisitions.filter((manifest) => manifest.instrument === id) : []);
  const sorted = $derived(
    [...acquisitions].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
  );
  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
</script>

{#snippet acquisitionStatus(status: AcquisitionManifest['status'])}
  <span class="flex items-center gap-2 text-fg-muted capitalize">
    {#if status === 'completed'}
      <Check width="14" height="14" class="text-fg-faint" />
    {:else if status === 'running'}
      <Record width="14" height="14" class="text-info" />
    {:else if status === 'preparing'}
      <DotsSpinner width="14" height="14" class="text-info" />
    {:else if status === 'failed'}
      <AlertCircleOutline width="14" height="14" class="text-danger" />
    {:else if status === 'interrupted'}
      <AlertOutline width="14" height="14" class="text-warning" />
    {:else}
      <Minus width="14" height="14" class="text-fg-faint" />
    {/if}
    {status}
  </span>
{/snippet}

<div class="p-4">
  {#if sorted.length > 0}
    <div class="overflow-hidden rounded-lg border border-border bg-card">
      {#each sorted as manifest, index (manifest.id)}
        <a
          href={instrumentAcquisitionPath(stationId, manifest.instrument, manifest.id)}
          class={cn(
            'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3 transition-colors hover:bg-element-hover',
            index > 0 && 'border-t border-border'
          )}
        >
          <span class="truncate text-fg">{dateFormat.format(new Date(manifest.created_at))}</span>
          {@render acquisitionStatus(manifest.status)}
        </a>
      {/each}
    </div>
  {:else}
    <div class="rounded-lg border border-dashed border-border px-6 py-12 text-center text-fg-muted">
      No acquisitions have been recorded for this instrument.
    </div>
  {/if}
</div>
