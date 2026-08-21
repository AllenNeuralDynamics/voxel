<script lang="ts">
  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instruments/instrument-view';
  import OverviewImaging from '$lib/instruments/overview/OverviewImaging.svelte';
  import { JsonView } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { cn } from '$lib/utils';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const acquisitions = $derived(id ? app.acquisitions.filter((manifest) => manifest.instrument === id) : []);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const state = $derived(activeInstrument?.state ?? selected?.state ?? null);
  const historical = $derived(!selected && acquisitions.length > 0);
  const overviewTab = $derived(page.url.hash === '#hardware' ? 'hardware' : 'imaging');
</script>

{#if id && hal && state}
  <div>
    <nav class="sticky top-0 z-10 flex border-b border-border bg-surface px-2" aria-label="Overview views">
      <a
        href="#imaging"
        class={cn(
          '-mb-px border-b-2 px-2 py-2 text-sm font-medium transition-colors',
          overviewTab === 'imaging'
            ? 'border-fg text-fg'
            : 'border-transparent text-fg-muted hover:border-border-focused hover:text-fg'
        )}
        aria-current={overviewTab === 'imaging' ? 'page' : undefined}
      >
        Imaging
      </a>
      <a
        href="#hardware"
        class={cn(
          '-mb-px border-b-2 px-1.5 py-2 text-sm font-medium transition-colors',
          overviewTab === 'hardware'
            ? 'border-fg text-fg'
            : 'border-transparent text-fg-muted hover:border-border-focused hover:text-fg'
        )}
        aria-current={overviewTab === 'hardware' ? 'page' : undefined}
      >
        Hardware
      </a>
    </nav>

    <div class="max-w-6xl px-4 py-5">
      {#if overviewTab === 'imaging'}
        <div id="imaging" class="scroll-mt-12">
          <OverviewImaging imaging={state.imaging} />
        </div>
      {:else}
        <section id="hardware" class="scroll-mt-12" aria-labelledby="hardware-heading">
          <h2 id="hardware-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-faint uppercase">
            Hardware topology
          </h2>
          <div class="overflow-x-auto rounded-lg border border-border/60 p-3">
            <JsonView data={hal} expandDepth={1} />
          </div>
        </section>
      {/if}
    </div>
  </div>
{:else if historical}
  <div class="p-4 text-fg-muted">
    This instrument is no longer in the catalog. Its recorded acquisitions remain available.
  </div>
{:else if selected?.errorSource === 'config'}
  <div class="p-4 text-fg-muted">Resolve the configuration issues above to inspect this instrument.</div>
{:else if !hal}
  <div class="p-4 text-fg-muted">The configuration could not be parsed.</div>
{:else}
  <div class="p-4 text-fg-muted">The state could not be parsed.</div>
{/if}
