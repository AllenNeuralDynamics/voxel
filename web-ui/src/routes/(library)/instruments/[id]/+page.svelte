<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { AlertCircleOutline } from '$lib/icons';
  import { Button, Dialog } from '$lib/kit';
  import { ApiError, getVoxelApp, type PresetRecord, type Violation } from '$lib/model';
  import { sanitizeString } from '$lib/utils';

  import InstrumentTabs from '../InstrumentTabs.svelte';
  import { resolveInstrumentView, violationLocation } from '../view';

  type Failure = {
    title: string;
    description: string;
    source: 'config' | 'state' | 'startup';
    violations: Violation[];
  };

  type HeaderAction = {
    label: string;
    onclick: () => void | Promise<void>;
  };

  const app = getVoxelApp();

  const id = $derived(page.params.id);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const isActive = $derived(!!id && app.activeName === id);
  const activeInstrument = $derived(isActive ? app.instrument : null);
  const acquisitions = $derived(id ? app.acquisitions.filter((manifest) => manifest.instrument === id) : []);

  let launchFailure = $state<Violation[] | null>(null);
  let archiveStateDialogOpen = $state(false);
  let presets = $state.raw<PresetRecord[]>([]);

  watch(
    () => id,
    (instrumentName) => {
      launchFailure = null;
      presets = [];
      if (instrumentName) void refreshPresets(instrumentName);
    }
  );

  async function refreshPresets(instrumentName = id): Promise<void> {
    if (!instrumentName) return;
    try {
      const loaded = await app.fetchPresets(instrumentName);
      if (id === instrumentName) presets = loaded;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }

  const action = $derived.by((): HeaderAction | null => {
    if (!selected?.config || selected.errorSource || isActive) return null;
    return { label: 'Open', onclick: openInstrument };
  });

  const failure = $derived.by((): Failure | null => {
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
      await goto(resolve('/configure'));
    } catch (error) {
      launchFailure = parseViolations(error);
    }
  }

  async function submitArchiveState(): Promise<void> {
    if (!id) return;
    try {
      await app.archiveState(id);
      archiveStateDialogOpen = false;
      launchFailure = null;
    } catch {
      if (app.error) toast.error(app.error);
    }
  }
</script>

<div class="flex h-full min-h-0 flex-col gap-1">
  <header class="flex shrink-0 items-center justify-between gap-3">
    <h1 class="truncate text-2xl font-medium text-fg">
      {selected
        ? sanitizeString(selected.name)
        : id && acquisitions.length
          ? sanitizeString(id)
          : 'Instrument not found'}
    </h1>
    {#if isActive}
      <span
        class="inline-flex items-center gap-2 rounded border border-success/30 bg-success/10 px-2 py-1 text-success"
      >
        <span class="size-1.5 rounded-full bg-success"></span>
        Active
      </span>
    {:else if !selected && acquisitions.length > 0}
      <span class="rounded bg-element-bg px-2 py-1 text-fg-muted">Historical</span>
    {:else if action}
      <Button variant="success" size="sm" disabled={app.busy} onclick={action.onclick}>
        {app.busy ? `${action.label}…` : action.label}
      </Button>
    {/if}
  </header>

  <div class="min-h-0 flex-1">
    {#if selected || acquisitions.length > 0}
      <div class="flex h-full min-h-0 flex-col">
        {#if failure}
          <section
            class="mb-2 flex max-h-[min(18rem,45vh)] shrink-0 flex-col overflow-hidden rounded-lg border border-danger/40 bg-danger/5"
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
                {:else if failure.source === 'startup'}
                  <Button variant="outline" size="xs" disabled={app.busy} onclick={openInstrument}>
                    {app.busy ? 'Retrying…' : 'Retry'}
                  </Button>
                {/if}
              </div>
            </div>
            <ul class="min-h-0 divide-y divide-border/40 overflow-y-auto">
              {#each failure.violations as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
                <li class="px-3 py-2">
                  <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    {#if violationLocation(violation)}
                      <span class="font-mono text-xs wrap-anywhere text-fg-muted">
                        {violationLocation(violation)}
                      </span>
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
        {/if}

        <div class="min-h-0 flex-1">
          {#key id}
            <InstrumentTabs
              hal={activeInstrument?.hal ?? selected?.config?.hal ?? null}
              instrumentState={activeInstrument
                ? {
                    kind: 'state',
                    value: activeInstrument.state,
                    activeDefaults: activeInstrument.default
                  }
                : selected?.state && selected.stateSource
                  ? { kind: selected.stateSource, value: selected.state }
                  : null}
              configurationInvalid={selected?.errorSource === 'config'}
              {acquisitions}
              instrumentName={id}
              {presets}
              {activeInstrument}
              onpresetschanged={refreshPresets}
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

<Dialog.Root bind:open={archiveStateDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Archive State</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        Archive <span class="font-medium text-fg">{id ? sanitizeString(id) : ''}</span>'s current state so it reopens
        with its configured defaults. The archived state is retained as
        <span class="font-mono text-fg">state.bak.json</span> or the next available numbered backup.
      </p>
    </div>

    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (archiveStateDialogOpen = false)}>Cancel</Button>
      <Button variant="danger" disabled={app.busy} onclick={submitArchiveState}>
        {app.busy ? 'Archiving…' : 'Archive State'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
