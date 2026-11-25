<script lang="ts">
  import { page } from '$app/state';
  import { getVoxelStation, useAppBar } from '$lib/context.svelte';
  import { ObjectView } from '@voxel/kit';

  // The default state of the instrument, as data. The model is of the open instrument, which may not be the one that the address names.
  const station = getVoxelStation();
  const instrument = $derived(
    station.session?.instrument_name === page.params.instrument ? station.instrument : undefined
  );

  useAppBar(() => ({ crumbs: [{ label: 'Config' }] }));
</script>

<div class="page-body min-h-0 flex-1 pt-4">
  {#if instrument}<ObjectView data={instrument.defaultState.value} expandDepth={2} />{/if}
</div>
