<script lang="ts">
  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { Button, Dialog, JsonView } from '$lib/kit';
  import { getVoxelStation, type InstrumentDefaults } from '$lib/model';
  import { toastError } from '$lib/utils';

  import PageHeader from '../../PageHeader.svelte';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  let defaultDialogMode = $state<'save' | 'restore' | null>(null);
  const stateSource = $derived(activeInstrument ? 'state' : selected?.stateSource);
  const defaultState = $derived.by((): InstrumentDefaults | null => {
    const current = activeInstrument?.state ?? selected?.state;
    if (!current) return null;
    // Only InstrumentDefaults fields are promotable; exclude run state and runtime data.
    return {
      imaging: current.imaging,
      routing: current.routing,
      metadata_cls: current.metadata_cls,
      output: current.output,
      stencil: current.stencil,
      traversal: current.traversal
    };
  });
  const canManageDefaults = $derived(activeInstrument?.mode === 'idle' || activeInstrument?.mode === 'preview');
  const historical = $derived(!selected && app.acquisitions.some((manifest) => manifest.instrument === id));
  const restoring = $derived(defaultDialogMode === 'restore');
  const defaultDialogTitle = $derived(restoring ? 'Restore default' : 'Save as default');

  function confirmDefault(): void {
    if (!activeInstrument || !canManageDefaults || defaultDialogMode === null) return;
    const action = restoring ? activeInstrument.restoreDefault() : activeInstrument.saveAsDefault();
    defaultDialogMode = null;
    toastError(action);
  }

  interface JsonDiff {
    path: string[];
    current: unknown;
    base: unknown;
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function jsonDivergence(current: unknown, base: unknown, path: string[] = []): JsonDiff[] {
    if (isRecord(current) && isRecord(base)) {
      const keys = [...new Set([...Object.keys(base), ...Object.keys(current)])];
      return keys.flatMap((key) => jsonDivergence(current[key], base[key], [...path, key]));
    }
    if (JSON.stringify(current) === JSON.stringify(base)) return [];
    return [{ path, current, base }];
  }

  const defaultChanges = $derived(
    activeInstrument && defaultState ? jsonDivergence(defaultState, activeInstrument.default) : []
  );

  function formatDiffValue(value: unknown): string {
    return typeof value === 'string' ? value : (JSON.stringify(value) ?? 'missing');
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Instrument' }]} class="px-4 pt-3 pb-2" />
  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if hal}
      <div class="max-w-6xl space-y-6 px-4 pt-2 pb-5">
        <section class="space-y-2.5" aria-labelledby="instrument-state-heading">
          <div class="flex flex-wrap items-center gap-2">
            <h2 id="instrument-state-heading" class="text-base text-fg">
              {stateSource === 'default' ? 'Default State' : 'Current State'}
            </h2>
            {#if activeInstrument && defaultState}
              <div class="ml-auto flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="xs"
                  disabled={!canManageDefaults}
                  onclick={() => (defaultDialogMode = 'restore')}>Restore default</Button
                >
                <Button
                  variant="outline"
                  size="xs"
                  disabled={!canManageDefaults}
                  onclick={() => (defaultDialogMode = 'save')}>Save as default</Button
                >
              </div>
            {/if}
          </div>
          {#if defaultState}
            <div class="overflow-x-auto rounded-lg border border-border/60 p-3">
              <JsonView data={defaultState} baseline={activeInstrument?.default} expandDepth={1} />
            </div>
          {:else}
            <p class="text-fg-muted">The state could not be parsed.</p>
          {/if}
        </section>
        <section class="space-y-2.5" aria-labelledby="hardware-configuration-heading">
          <h2 id="hardware-configuration-heading" class="text-base text-fg">Hardware configuration</h2>
          <div class="overflow-x-auto rounded-lg border border-border/60 p-3">
            <JsonView data={hal} expandDepth={1} />
          </div>
        </section>
      </div>
    {:else if historical}
      <div class="p-4 text-fg-muted">
        This instrument is no longer in the catalog. Its recorded acquisitions remain available.
      </div>
    {:else if selected?.errorSource === 'config'}
      <div class="p-4 text-fg-muted">Resolve the configuration issues above to inspect this instrument.</div>
    {:else}
      <div class="p-4 text-fg-muted">The configuration could not be parsed.</div>
    {/if}
  </div>
  {#if activeInstrument}
    <Dialog.Root open={defaultDialogMode !== null} onOpenChange={(open) => !open && (defaultDialogMode = null)}>
      <Dialog.Content size="xxl" showCloseButton={false}>
        <Dialog.Header>
          <Dialog.Title>{defaultDialogTitle}</Dialog.Title>
          <Dialog.Description>
            {restoring
              ? 'Overwrite the current state with the saved default.'
              : 'Save the current state as the new default.'}
          </Dialog.Description>
        </Dialog.Header>
        <div class="max-h-[60dvh] overflow-auto rounded border border-border bg-surface px-3 py-2">
          {#if defaultChanges.length === 0}
            <p class="text-base text-fg-muted">Matches default.</p>
          {:else}
            <div class="space-y-1">
              {#each defaultChanges as { path, current, base } (JSON.stringify(path))}
                <div class="flex flex-wrap items-baseline gap-2 font-mono text-base wrap-anywhere">
                  <span class="text-fg-muted">{path.join('/')}</span>
                  <span class="text-warning">{formatDiffValue(current)}</span>
                  <span class="text-fg-faint">({formatDiffValue(base)})</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
        <Dialog.Footer>
          <Button variant="ghost" onclick={() => (defaultDialogMode = null)}>Cancel</Button>
          <Button variant={restoring ? 'danger' : 'default'} disabled={!canManageDefaults} onclick={confirmDefault}>
            {defaultDialogTitle}
          </Button>
        </Dialog.Footer>
      </Dialog.Content>
    </Dialog.Root>
  {/if}
</div>
