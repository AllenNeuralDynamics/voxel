<script lang="ts">
  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { JsonView } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { displayName } from '$lib/utils';

  import PageHeader from '../../../PageHeader.svelte';
  import RoutingRuleEditor from './RoutingRuleEditor.svelte';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const instrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(instrument?.hal ?? selected?.config?.hal ?? null);
  const state = $derived(instrument?.state ?? selected?.state ?? null);
  const historical = $derived(!selected && app.acquisitions.some((manifest) => manifest.instrument === id));
</script>

<section class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Optical routing' }]} />
  <div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-5">
    {#if instrument}
      {#key instrument}
        <div class="divide-y divide-border-faint">
          {#each instrument.routingDimensions as dimension (dimension.id)}
            <section
              id={`routing-${dimension.id}`}
              class="scroll-mt-4 py-4 first:pt-0"
              aria-label={displayName(dimension.id)}
            >
              <RoutingRuleEditor {instrument} {dimension} />
            </section>
          {:else}
            <p class="text-base text-fg-muted">This instrument has no optical routing rules.</p>
          {/each}
        </div>
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
        class="min-w-0 space-y-3 rounded-lg border border-border-faint/50 p-3"
        aria-labelledby="routing-configuration-heading"
      >
        <h2 id="routing-configuration-heading" class="text-sm text-fg-muted">Routing configuration</h2>
        {#if hal}
          <section class="space-y-2" aria-labelledby="routing-declarations-heading">
            <h3 id="routing-declarations-heading" class="text-sm text-fg-muted">Declarations</h3>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need to scroll wide configuration values.) -->
            <div class="overflow-x-auto" role="region" aria-label="Routing declarations" tabindex="0">
              <JsonView data={hal.optical_routing} expandDepth={1} />
            </div>
          </section>
        {/if}
        {#if state}
          <section class="space-y-2" aria-labelledby="routing-rules-heading">
            <h3 id="routing-rules-heading" class="text-sm text-fg-muted">Rules</h3>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need to scroll wide configuration values.) -->
            <div class="overflow-x-auto" role="region" aria-label="Routing rules" tabindex="0">
              <JsonView data={state.routing} expandDepth={1} />
            </div>
          </section>
        {/if}
      </section>
    {/if}
  </div>
</section>
