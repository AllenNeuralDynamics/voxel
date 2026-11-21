<script lang="ts">
  import { resolve } from '$app/paths';
  import { getPageInstrument } from '$lib/context.svelte';
  import PageFallback from '$lib/shell/PageFallback.svelte';
  import { displayName } from '@voxel/kit/format';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();

  const selected = getPageInstrument();
  const profile = $derived(selected.imaging?.profiles[params.profileId]);
  const label = $derived(profile?.label || displayName(params.profileId));
  const items = $derived([
    { label: 'Profiles', href: resolve('/stations/[stationId]/instruments/[instrumentId]/profiles', selected.params) },
    { label }
  ]);
  // The sync page edits the active profile's waveforms, so it opens only for the active profile. Without this, the
  // link of another profile would show the active profile's waveforms under its name.
  const operatingPage = $derived(Boolean(params.generatorId));
</script>

{#if !profile}
  <PageFallback {items}>Profile “{label}” is not available.</PageFallback>
{:else if operatingPage && selected.open?.activeProfileId !== params.profileId}
  <PageFallback {items}>{label} is not active. Activate it to access operating controls.</PageFallback>
{:else}
  {@render children()}
{/if}
