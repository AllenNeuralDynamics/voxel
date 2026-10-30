<script lang="ts">
  import { getVoxelStation, providePageInstrument } from '$lib/context.svelte';
  import { displayName } from '$lib/core/utils';
  import PageFallback from '$lib/shell/PageFallback.svelte';

  import type { LayoutProps } from './$types';

  let { children, params }: LayoutProps = $props();
  const app = getVoxelStation();
  // The pages below read this instrument with getPageInstrument(), so they need no check of their own.
  const selected = providePageInstrument(() => params);
  const historical = $derived(app.acquisitions.some((manifest) => manifest.instrument === params.instrumentId));
</script>

<!-- The shell's <main> is the flex column, so the pages sit in it directly. -->
{#if selected.saved || historical}
  {@render children()}
{:else}
  <PageFallback items={[{ label: displayName(params.instrumentId) }]}>
    This instrument is not in the catalog.
  </PageFallback>
{/if}
