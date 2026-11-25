<script lang="ts">
  import { goto } from '$app/navigation';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';

  // The station's address goes to the open instrument, else the first one, once the station is known.
  const station = getVoxelStation();
  const selection = getInstrumentSelection();

  $effect(() => {
    if (!station.info) return;
    const name = station.session?.instrument.name ?? Object.keys(station.instruments).sort()[0];
    if (name) void goto(selection.href(name, 'run'), { replaceState: true });
  });
</script>
