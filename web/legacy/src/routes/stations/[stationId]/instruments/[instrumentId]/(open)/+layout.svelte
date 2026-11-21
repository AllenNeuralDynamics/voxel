<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument, getVoxelStation, provideOpenInstrument } from '$lib/context.svelte';
  import PageFallback from '$lib/shell/PageFallback.svelte';
  import { Button } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { ArrowRight } from '@voxel/kit/icons';

  const { children } = $props();
  const app = getVoxelStation();
  const selected = getPageInstrument();
  // The pages below read the open instrument with getOpenInstrument(). They show only while it is open.
  provideOpenInstrument();
  const instrumentId = $derived(selected.params.instrumentId);
  const saved = $derived(selected.saved);
  const brokenFile = $derived(
    saved?.errorSource === 'config' ? 'config.yaml' : saved?.errorSource === 'state' ? 'state.json' : null
  );
  // The page name comes from its folder: lasers is Lasers.
  const title = $derived(displayName(page.route.id?.split('/(open)/')[1]?.split('/')[0] ?? ''));
  const opening = $derived(app.openingName === instrumentId || app.stationStatus === 'opening');
</script>

{#if selected.open}
  {@render children()}
{:else}
  <PageFallback items={[{ label: title }]}>
    {#if brokenFile}
      <span>This instrument cannot open. <span class="font-mono">{brokenFile}</span> has issues.</span>
      <a
        href={resolve('/stations/[stationId]/instruments/[instrumentId]/config', selected.params)}
        class="inline-flex items-center gap-1 rounded-sm hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-focus"
        >Open Config<ArrowRight class="size-3" aria-hidden="true" /></a
      >
    {:else if opening}
      <span role="status">Opening the instrument…</span>
    {:else}
      <span>{title} needs the open instrument.</span>
      <!-- It opens from here only while no instrument is open. Switching instruments goes through the station menu. -->
      {#if app.canOpen(instrumentId)}
        <Button variant="quiet" size="xs" onclick={() => reportFailure(app.launch(instrumentId))}>
          Open instrument
        </Button>
      {/if}
    {/if}
  </PageFallback>
{/if}
