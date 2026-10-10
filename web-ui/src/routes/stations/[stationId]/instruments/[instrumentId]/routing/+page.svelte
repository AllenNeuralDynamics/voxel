<script lang="ts">
  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { JsonView } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';

  import RoutingControls from './RoutingControls.svelte';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const instrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(instrument?.hal ?? selected?.config?.hal ?? null);
  const state = $derived(instrument?.state ?? selected?.state ?? null);
  const historical = $derived(!selected && app.acquisitions.some((manifest) => manifest.instrument === id));
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Optical routing' }]} />
  <div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-5">
    {#if instrument}
      {#key instrument}
        <RoutingControls {instrument} />
      {/key}
    {:else if !state}
      {#if historical}
        <p class="text-base text-fg-muted">
          This instrument is no longer in the catalog. Its recorded acquisitions remain available.
        </p>
      {:else if selected?.errorSource === 'config'}
        <p class="text-base text-fg-muted">Resolve the configuration issues above to inspect this instrument.</p>
      {:else}
        <p class="text-base text-fg-muted">The configuration could not be parsed.</p>
      {/if}
    {/if}

    {#if hal || state}
      <section
        class="min-w-0 space-y-3 rounded-lg border border-line-faint p-3"
        aria-labelledby="routing-configuration-heading"
      >
        <h2 id="routing-configuration-heading" class="text-sm text-fg-muted">Routing configuration</h2>
        {#if hal}
          <h3 id="routing-declarations-heading" class="text-sm text-fg-muted">Declarations</h3>
          <JsonView data={hal.optical_routing} expandDepth={1} />
        {/if}
        {#if state}
          <h3 id="routing-rules-heading" class="text-sm text-fg-muted">Rules</h3>
          <JsonView data={state.routing} expandDepth={1} />
        {/if}
      </section>
    {/if}
  </div>
</div>
