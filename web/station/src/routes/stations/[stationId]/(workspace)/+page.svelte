<script lang="ts">
  import { goto } from '$app/navigation';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';

  const station = getVoxelStation();
  const selection = getInstrumentSelection();

  $effect(() => {
    if (!station.info) return;
    const name = station.session?.instrument.name ?? Object.keys(station.instruments).sort()[0];
    if (name) void goto(selection.href(name, 'run'), { replaceState: true });
  });
</script>
