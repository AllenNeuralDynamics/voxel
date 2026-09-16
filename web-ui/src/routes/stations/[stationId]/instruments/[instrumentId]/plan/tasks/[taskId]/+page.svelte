<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelStation } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';

  const app = getVoxelStation();
  const routeParams = $derived({
    stationId: page.params.stationId ?? '',
    instrumentId: page.params.instrumentId ?? ''
  });
  const instrument = $derived(app.instrument?.id === routeParams.instrumentId ? app.instrument : null);
  const taskId = $derived(page.params.taskId ?? '');
  const task = $derived(instrument?.state.tasks[taskId]);
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader
    items={[
      { label: 'Plan', href: resolve('/stations/[stationId]/instruments/[instrumentId]/plan', routeParams) },
      { label: 'Task', title: taskId }
    ]}
  />
  <div class="min-h-0 flex-1 overflow-auto px-4 pb-4">
    <p class="text-fg-muted">
      {#if !instrument}
        Open this instrument to view the task.
      {:else if !task}
        This task is no longer in the plan.
      {:else}
        Task editing will go here.
      {/if}
    </p>
  </div>
</div>
