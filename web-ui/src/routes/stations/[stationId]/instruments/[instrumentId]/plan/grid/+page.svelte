<script lang="ts">
  import { page } from '$app/state';
  import { GridCanvas } from '$lib/grid';
  import { getVoxelStation } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';

  const app = getVoxelStation();
  const instrument = $derived(app.instrument?.id === page.params.instrumentId ? app.instrument : null);
  const preferenceKey = $derived(`${page.params.stationId ?? ''}/${page.params.instrumentId ?? ''}`);
  const taskRange = $derived.by(() => {
    const saved = prefs.plan.taskDefaults.get()[preferenceKey];
    if (saved) return { start: saved.start, end: saved.end };
    const z = instrument?.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Grid' }]} />
  <div class="min-h-0 flex-1 overflow-hidden">
    {#if instrument}
      <GridCanvas {instrument} {taskRange} />
    {/if}
  </div>
</div>
