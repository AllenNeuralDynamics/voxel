<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import {
    provideChannelPrefs,
    provideColormaps,
    provideInstrumentSelection,
    provideShownProfile,
    provideStationContext
  } from '$lib/context.svelte';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();

  const station = provideStationContext();
  provideInstrumentSelection(station, () => params);
  provideChannelPrefs(station, provideColormaps());
  provideShownProfile(station);
  onMount(() => station.initialize(params.stationId));
  onDestroy(() => station.dispose());
</script>

{@render children()}
