<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { page } from '$app/state';
  import { AlertCircleOutline } from '$lib/icons';
  import { Button, Dialog } from '$lib/kit';
  import { ApiError, getVoxelApp, type Violation } from '$lib/model';
  import { sanitizeString } from '$lib/utils';

  import InstrumentTabs from '../../InstrumentTabs.svelte';
  import { resolveInstrumentView, violationLocation } from './view';

  type Failure = {
    title: string;
    description: string;
    source: 'config' | 'bench' | 'startup';
    violations: Violation[];
  };

  type HeaderAction = {
    label: string;
    variant: 'danger' | 'success';
    onclick: () => void | Promise<void>;
  };

  const app = getVoxelApp();

  const id = $derived(page.params.id);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const isActive = $derived(!!id && app.activeName === id);
  const activeInstrument = $derived(isActive ? app.instrument : null);

  let launchFailure = $state<Violation[] | null>(null);
  let archiveBenchDialogOpen = $state(false);
  let closeDialogOpen = $state(false);

  watch(
    () => id,
    () => {
      launchFailure = null;
    }
  );

  const action = $derived.by((): HeaderAction | null => {
    if (!selected?.config || selected.errorSource) return null;
    return isActive
      ? {
          label: 'Close',
          variant: 'danger',
          onclick: () => {
            closeDialogOpen = true;
          }
        }
      : { label: 'Open', variant: 'success', onclick: openInstrument };
  });

  const failure = $derived.by((): Failure | null => {
    if (selected?.errorSource && selected.errors.length > 0) {
      const source = selected.errorSource;
      return {
        title:
          source === 'config' && selected.config
            ? 'config.yaml is invalid'
            : `${source === 'config' ? 'config.yaml' : 'bench.json'} could not be loaded`,
        description:
          source === 'config'
            ? 'Fix the instrument configuration before it can be opened.'
            : 'Archive the saved bench to reopen this instrument with its configured defaults.',
        source,
        violations: selected.errors
      };
    }

    if (launchFailure) {
      return {
        title: `Unable to open ${id ? sanitizeString(id) : 'instrument'}`,
        description: 'Hardware startup did not complete. Review the reported issues and retry when they are resolved.',
        source: 'startup',
        violations: launchFailure
      };
    }

    return null;
  });

  function parseViolations(error: unknown): Violation[] {
    if (error instanceof ApiError && Array.isArray(error.detail)) {
      const violations = error.detail.filter(
        (item): item is Violation =>
          typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
      );
      if (violations.length > 0) return violations;
    }
    return [{ msg: error instanceof Error ? error.message : String(error) }];
  }

  async function openInstrument(): Promise<void> {
    if (!id) return;
    launchFailure = null;
    try {
      await app.launch(id);
    } catch (error) {
      launchFailure = parseViolations(error);
    }
  }

  async function submitArchiveBench(): Promise<void> {
    if (!id) return;
    try {
      await app.archiveBench(id);
      archiveBenchDialogOpen = false;
      launchFailure = null;
    } catch {
      if (app.error) toast.error(app.error);
    }
  }
</script>

<div class="flex h-full min-h-0 flex-col">
  <header class="shrink-0">
    <div class="flex min-h-12 items-center justify-between gap-3 px-4 py-2">
      <h1 class="truncate text-2xl font-medium text-fg">
        {selected ? sanitizeString(selected.name) : 'Instrument not found'}
      </h1>
      {#if action}
        <Button variant={action.variant} size="sm" disabled={app.busy} onclick={action.onclick}>
          {app.busy ? `${action.label}…` : action.label}
        </Button>
      {/if}
    </div>
  </header>

  <div class="min-h-0 flex-1">
    {#if selected}
      <div class="flex h-full min-h-0 flex-col">
        {#if failure}
          <div class="shrink-0 px-4 pt-4">
            <section class="overflow-hidden rounded-lg border border-danger/40 bg-danger/5">
              <div class="flex items-start gap-3 border-b border-danger/25 px-3 py-2.5">
                <AlertCircleOutline width="18" height="18" class="mt-0.5 shrink-0 text-danger" />
                <div class="min-w-0 flex-1">
                  <h2 class="text-lg font-medium text-danger">{failure.title}</h2>
                  <p class="mt-0.5 text-fg-muted">{failure.description}</p>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  {#if failure.source === 'bench'}
                    <Button variant="outline" size="xs" onclick={() => (archiveBenchDialogOpen = true)}>
                      Archive bench…
                    </Button>
                  {:else if failure.source === 'startup'}
                    <Button variant="outline" size="xs" disabled={app.busy} onclick={openInstrument}>
                      {app.busy ? 'Retrying…' : 'Retry'}
                    </Button>
                  {/if}
                </div>
              </div>
              <ul class="divide-y divide-border/40">
                {#each failure.violations as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
                  <li class="px-3 py-2">
                    <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      {#if violationLocation(violation)}
                        <span class="font-mono text-sm break-all text-fg-muted">{violationLocation(violation)}</span>
                      {/if}
                      {#if violation.code}
                        <span class="font-mono text-sm text-fg-muted">[{violation.code}]</span>
                      {/if}
                    </div>
                    <p class="text-base text-danger">{violation.msg}</p>
                  </li>
                {/each}
              </ul>
            </section>
          </div>
        {/if}

        <div class="min-h-0 flex-1">
          {#key id}
            <InstrumentTabs
              hal={activeInstrument?.hal ?? selected.config?.hal ?? null}
              instrumentState={activeInstrument
                ? {
                    kind: 'bench',
                    value: activeInstrument.state,
                    activeDefaults: activeInstrument.default
                  }
                : selected.bench && selected.stateSource
                  ? { kind: selected.stateSource, value: selected.bench }
                  : null}
            />
          {/key}
        </div>
      </div>
    {:else}
      <div class="flex h-full items-center justify-center p-8">
        <p class="text-lg text-fg-muted">This instrument is not in the catalog.</p>
      </div>
    {/if}
  </div>
</div>

<Dialog.Root bind:open={archiveBenchDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Archive Bench</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        Archive <span class="font-medium text-fg">{id ? sanitizeString(id) : ''}</span>'s current bench so it reopens
        with its configured defaults. The archived state is retained as
        <span class="font-mono text-fg">bench.bak.json</span> or the next available numbered backup.
      </p>
    </div>

    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (archiveBenchDialogOpen = false)}>Cancel</Button>
      <Button variant="danger" disabled={app.busy} onclick={submitArchiveBench}>
        {app.busy ? 'Archiving…' : 'Archive Bench'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={closeDialogOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Close Session</Dialog.Title>
    </Dialog.Header>
    <p class="text-lg text-fg-muted">
      Are you sure you want to close the current session? Any unsaved progress will be lost.
    </p>
    <Dialog.Footer>
      <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
      <Button
        variant="danger"
        onclick={() => {
          closeDialogOpen = false;
          app.close();
        }}
      >
        Close Session
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
