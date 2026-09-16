<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelStation } from '$lib/model';
  import PageHeader, { type PageHeaderItem } from '$lib/PageHeader.svelte';

  const { children } = $props();
  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const routeParams = $derived({ stationId, instrumentId });
  const acquisitionId = $derived(page.params.acquisitionId);
  const acquisition = $derived(
    app.acquisitions.find((candidate) => candidate.id === acquisitionId && candidate.instrument === instrumentId)
  );
  const dateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  });
  const breadcrumbItems = $derived.by<PageHeaderItem[]>(() => {
    if (!acquisitionId) return [{ label: 'Acquisitions' }];
    return [
      {
        label: 'Acquisitions',
        href: resolve('/stations/[stationId]/instruments/[instrumentId]/acquisitions', routeParams)
      },
      {
        label: acquisition ? dateFormat.format(new Date(acquisition.created_at)) : 'Acquisition',
        title: acquisitionId
      }
    ];
  });
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col bg-canvas">
  <PageHeader items={breadcrumbItems} />
  <div class="min-h-0 flex-1 overflow-y-auto">
    {@render children()}
  </div>
</div>
