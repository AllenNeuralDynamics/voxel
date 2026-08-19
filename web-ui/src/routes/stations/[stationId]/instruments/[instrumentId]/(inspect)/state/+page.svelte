<script lang="ts">
  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instruments/view';
  import { Button, JsonView } from '$lib/kit';
  import { getVoxelStation, type InstrumentDefaults } from '$lib/model';

  import DefaultConfigDialog, { type DefaultDialogMode } from './DefaultConfigDialog.svelte';

  type StateView =
    | { kind: 'default'; value: InstrumentDefaults }
    | { kind: 'state'; value: InstrumentDefaults; activeDefaults?: InstrumentDefaults };

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  let defaultDialogMode = $state<DefaultDialogMode | null>(null);
  const stateView = $derived<StateView | null>(
    activeInstrument
      ? { kind: 'state' as const, value: activeInstrument.state, activeDefaults: activeInstrument.default }
      : selected?.state && selected.stateSource
        ? { kind: selected.stateSource, value: selected.state }
        : null
  );
</script>

<div class="py-4 pt-3">
  {#if stateView}
    <section>
      <div class="mb-2 flex items-center gap-3">
        <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">
          {stateView.kind === 'default' ? 'Default State' : 'Current State'}
        </h2>
        {#if stateView.kind === 'state' && stateView.activeDefaults}
          <div class="ml-auto flex items-center gap-1.5">
            <Button variant="ghost" size="xs" onclick={() => (defaultDialogMode = 'restore')}>Restore default</Button>
            <Button variant="outline" size="xs" onclick={() => (defaultDialogMode = 'save')}>Save as default</Button>
          </div>
        {/if}
      </div>
      {#if stateView.kind === 'state' && stateView.activeDefaults}
        <JsonView data={stateView.value} baseline={stateView.activeDefaults} expandDepth={1} />
      {:else}
        <JsonView data={stateView.value} expandDepth={1} />
      {/if}
    </section>
  {:else if selected?.errorSource === 'config'}
    <p class="text-fg-muted">The instrument state is unavailable until its configuration issues are resolved.</p>
  {:else}
    <p class="text-fg-muted">The state could not be parsed.</p>
  {/if}
</div>

<DefaultConfigDialog bind:mode={defaultDialogMode} />
