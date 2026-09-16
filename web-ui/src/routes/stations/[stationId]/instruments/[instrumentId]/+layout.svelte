<script lang="ts">
  import { toast } from 'svelte-sonner';

  import { page } from '$app/state';
  import { AlertCircleOutline } from '$lib/icons';
  import { resolveInstrumentView, violationLocation } from '$lib/instrument-view';
  import { Button, Dialog } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { displayName } from '$lib/utils';

  const { children } = $props();
  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const historical = $derived(app.acquisitions.some((manifest) => manifest.instrument === id));

  let archiveStateDialogOpen = $state(false);

  const failure = $derived.by(() => {
    if (selected?.errorSource && selected.errors.length > 0) {
      const source = selected.errorSource;
      return {
        title:
          source === 'config' && selected.config
            ? 'config.yaml is invalid'
            : `${source === 'config' ? 'config.yaml' : 'state.json'} could not be loaded`,
        description:
          source === 'config'
            ? 'Fix the instrument configuration before it can be opened.'
            : 'Archive the saved state to reopen this instrument with its configured defaults.',
        source,
        violations: selected.errors
      };
    }

    return null;
  });

  async function submitArchiveState(): Promise<void> {
    if (!id) return;
    try {
      await app.archiveState(id);
      archiveStateDialogOpen = false;
    } catch {
      if (app.error) toast.error(app.error);
    }
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-canvas">
  {#if failure}
    <div class="shrink-0 px-4 pt-1">
      <section
        class="flex max-h-[min(18rem,45vh)] flex-col overflow-hidden rounded-lg border border-danger/40 bg-danger/5"
      >
        <div class="flex shrink-0 items-start gap-3 border-b border-danger/25 p-3">
          <AlertCircleOutline width="18" height="18" class="mt-0.5 shrink-0 text-danger" />
          <div class="min-w-0 flex-1">
            <h2 class="text-base font-medium text-danger">{failure.title}</h2>
            <p class="mt-0.5 text-sm text-fg-muted">{failure.description}</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <span class="text-sm text-fg-muted">
              {failure.violations.length}
              {failure.violations.length === 1 ? 'issue' : 'issues'}
            </span>
            {#if failure.source === 'state'}
              <Button variant="outline" size="xs" onclick={() => (archiveStateDialogOpen = true)}>
                Archive state…
              </Button>
            {/if}
          </div>
        </div>
        <ul class="min-h-0 divide-y divide-line-faint overflow-y-auto">
          {#each failure.violations as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
            <li class="px-3 py-2">
              <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                {#if violationLocation(violation)}
                  <span class="font-mono text-xs wrap-anywhere text-fg-muted">{violationLocation(violation)}</span>
                {/if}
                {#if violation.code}
                  <span class="rounded bg-danger/10 px-1.5 py-0.5 font-mono text-xs text-danger">
                    {violation.code}
                  </span>
                {/if}
              </div>
              <p class="mt-1 text-sm text-fg">{violation.msg}</p>
            </li>
          {/each}
        </ul>
      </section>
    </div>
  {/if}

  <div class="min-h-0 min-w-0 flex-1 overflow-hidden">
    {#if selected || historical}
      {@render children()}
    {:else}
      <div class="flex h-full min-h-0 items-center justify-center p-8">
        <p class="text-lg text-fg-muted">This instrument is not in the catalog.</p>
      </div>
    {/if}
  </div>
</div>

<Dialog.Root bind:open={archiveStateDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Archive State</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-line-faint" />
    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        Archive <span class="font-medium text-fg">{id ? displayName(id) : ''}</span>'s current state so it reopens with
        its configured defaults. The archived state is retained as
        <span class="font-mono text-fg">state.bak.json</span> or the next available numbered backup.
      </p>
    </div>
    <hr class="-mx-4 border-line-faint" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (archiveStateDialogOpen = false)}>Cancel</Button>
      <Button variant="danger" disabled={app.busy} onclick={submitArchiveState}>
        {app.busy ? 'Archiving…' : 'Archive State'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
