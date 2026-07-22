<script lang="ts">
  import { Select } from 'bits-ui';
  import { toast } from 'svelte-sonner';

  import { AlertCircleOutline, ChevronDown, Cog } from '$lib/icons';
  import InstrumentInspector from '$lib/InstrumentInspector.svelte';
  import { Button, Dialog, Field, TextInput } from '$lib/kit';
  import LogViewer from '$lib/LogViewer.svelte';
  import type { HALConfig, InstrumentInfo, InstrumentState, LoadError, VoxelApp } from '$lib/model';
  import { configError, isLoaded } from '$lib/model';
  import { themes } from '$lib/themes';
  import { sanitizeString } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  interface Props {
    app: VoxelApp;
  }

  const { app }: Props = $props();

  type Selection = { kind: 'instrument'; name: string } | { kind: 'template'; name: string } | null;

  let selection = $state<Selection>(null);

  // Create-from-template dialog state.
  let dialogOpen = $state(false);
  let dialogTemplate = $state('');
  let dialogName = $state('');

  const instrumentEntries = $derived(Object.entries(app.catalog.instruments));
  const templateEntries = $derived(Object.entries(app.catalog.templates));

  // Picker value encodes the kind so instrument/template names can't collide.
  const pickerValue = $derived(selection ? `${selection.kind}:${selection.name}` : '');

  function onPick(value: string | undefined): void {
    if (!value) return;
    const sep = value.indexOf(':');
    const kind = value.slice(0, sep);
    const name = value.slice(sep + 1);
    if (kind === 'template') selectTemplate(name);
    else selectInstrument(name);
  }

  // The primary action for the current selection: open an instrument, or create from a template.
  const action = $derived.by(() => {
    const s = selected;
    if (!s?.ok) return null;
    return s.kind === 'template'
      ? { label: 'Create', busy: false, onclick: () => openCreateDialog(s.name) }
      : { label: 'Open', busy: app.busy, onclick: () => openInstrument(s.name) };
  });

  // Auto-select once the catalog loads: prefer the last-opened instrument, else the first.
  $effect(() => {
    if (selection === null && instrumentEntries.length > 0) {
      const last = app.lastInstrument;
      const name = last && last in app.catalog.instruments ? last : instrumentEntries[0][0];
      selection = { kind: 'instrument', name };
    }
  });

  // Resolve the HAL + bench (or load errors) for the current selection.
  type Selected =
    | { ok: true; name: string; kind: 'instrument' | 'template'; hal: HALConfig; bench: InstrumentState }
    | { ok: false; name: string; source: 'config' | 'bench'; errors: LoadError };

  const selected = $derived.by((): Selected | null => {
    if (!selection) return null;
    if (selection.kind === 'template') {
      const config = app.catalog.templates[selection.name];
      if (!config) return null;
      return { ok: true, name: selection.name, kind: 'template', hal: config.hal, bench: config.default };
    }
    const info = app.catalog.instruments[selection.name];
    if (!info) return null;
    if (!isLoaded(info)) return { ok: false, name: selection.name, source: 'config', errors: configError(info) ?? {} };
    const benchErr = benchError(info);
    if (benchErr) return { ok: false, name: selection.name, source: 'bench', errors: benchErr };
    // A never-opened instrument (no bench.json) has no saved bench — preview the config's defaults instead.
    const bench = isLoadedBench(info.bench) ? info.bench : info.config.default;
    return { ok: true, name: selection.name, kind: 'instrument', hal: info.config.hal, bench };
  });

  /** The bench's load errors, or null when the bench loaded cleanly or was never saved (no bench.json). */
  function benchError(info: InstrumentInfo): LoadError | null {
    const bench = info.bench;
    if (bench === null || isLoadedBench(bench)) return null;
    return bench;
  }

  /** Whether an instrument failed to load its config or has a stale/invalid saved bench. */
  function hasError(info: InstrumentInfo): boolean {
    return !isLoaded(info) || benchError(info) !== null;
  }

  $effect(() => {
    if (app.client.state === 'connected') app.refresh();
  });

  function isLoadedBench(bench: InstrumentInfo['bench']): bench is InstrumentState {
    return typeof bench === 'object' && bench !== null && 'imaging' in bench;
  }

  function sanitize(name: string): string {
    return name.trim().toLowerCase().replace(/\s+/g, '-');
  }

  function selectInstrument(name: string) {
    selection = { kind: 'instrument', name };
  }

  function selectTemplate(name: string) {
    selection = { kind: 'template', name };
  }

  async function openInstrument(name: string) {
    try {
      await app.launch(name);
    } catch {
      if (app.error) toast.error(app.error);
    }
  }

  function openCreateDialog(template: string) {
    dialogTemplate = template;
    dialogName = template;
    dialogOpen = true;
  }

  async function createFromTemplate() {
    const name = sanitize(dialogName) || dialogTemplate;
    try {
      await app.launchTemplate(dialogTemplate, name);
      dialogOpen = false;
    } catch {
      if (app.error) toast.error(app.error);
    }
  }
</script>

<div class="grid h-screen w-full grid-cols-[auto_1fr] bg-canvas">
  <!-- Inspector -->
  <div class="flex min-w-4xl flex-col bg-surface/60">
    <!-- Header -->
    <div class="shrink-0">
      <!-- Row 1: brand + appearance -->
      <div class="flex items-center justify-between px-4 py-2">
        <div class="flex items-center gap-2">
          <VoxelLogo class="h-6 w-6" />
          <h1 class="text-3xl font-normal tracking-wider text-fg uppercase">Voxel</h1>
        </div>
        <button
          title="Appearance"
          onclick={() => (themes.pickerOpen = true)}
          class="flex items-center rounded p-1 text-fg-muted transition-colors hover:text-fg"
        >
          <Cog width="16" height="16" />
        </button>
      </div>

      <!-- Row 2: instrument/template picker + action -->
      <div class="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <Select.Root type="single" value={pickerValue} onValueChange={onPick}>
          <Select.Trigger
            class="flex min-w-56 items-center justify-between gap-2 rounded px-1.5 py-0.5 text-2xl font-medium text-fg transition-colors hover:bg-element-hover focus:outline-none"
          >
            <span class="truncate">
              {#if selection}{sanitizeString(selection.name)}{:else}<span class="text-fg-muted"
                  >Select an instrument</span
                >{/if}
            </span>
            <ChevronDown width="16" height="16" class="shrink-0 opacity-50" />
          </Select.Trigger>
          <Select.Portal>
            <Select.Content
              align="start"
              class="z-50 mt-1 min-w-(--bits-select-anchor-width) rounded border bg-floating p-1 text-fg shadow-md"
            >
              <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
                <Select.Group>
                  <Select.GroupHeading
                    class="px-1.5 py-1 text-[10px] font-medium tracking-wide text-fg-muted/70 uppercase"
                  >
                    Instruments
                  </Select.GroupHeading>
                  {#each instrumentEntries as [name, info] (name)}
                    <Select.Item
                      value={`instrument:${name}`}
                      label={sanitizeString(name)}
                      class="relative flex w-full cursor-default items-center gap-2 rounded px-1.5 py-1 text-base outline-none select-none data-highlighted:bg-element-hover"
                    >
                      <span class="min-w-0 flex-1 truncate text-fg">{sanitizeString(name)}</span>
                      {#if hasError(info)}
                        <span class="size-1.5 shrink-0 rounded-full bg-danger" title="Failed to load"></span>
                      {/if}
                    </Select.Item>
                  {/each}
                </Select.Group>

                {#if templateEntries.length > 0}
                  <div class="my-1 h-px bg-border"></div>
                  <Select.Group>
                    <Select.GroupHeading
                      class="px-1.5 py-1 text-[10px] font-medium tracking-wide text-fg-muted/70 uppercase"
                    >
                      Templates
                    </Select.GroupHeading>
                    {#each templateEntries as [name] (name)}
                      <Select.Item
                        value={`template:${name}`}
                        label={sanitizeString(name)}
                        class="relative flex w-full cursor-default items-center gap-2 rounded px-1.5 py-1 text-base outline-none select-none data-highlighted:bg-element-hover"
                      >
                        <span class="min-w-0 flex-1 truncate text-fg">{sanitizeString(name)}</span>
                      </Select.Item>
                    {/each}
                  </Select.Group>
                {/if}
              </Select.Viewport>
            </Select.Content>
          </Select.Portal>
        </Select.Root>

        <span class="flex-1"></span>

        {#if action}
          <Button variant="success" size="sm" disabled={action.busy} onclick={action.onclick}>
            {action.busy ? `${action.label}…` : action.label}
          </Button>
        {/if}
      </div>
    </div>

    <div class="flex min-h-0 flex-1 flex-col">
      {#if selected}
        {#if !selected.ok}
          {@const errorEntries = Object.entries(selected.errors)}
          <div class="flex h-full flex-col gap-3 overflow-y-auto p-4">
            <div class="flex items-center gap-2">
              <AlertCircleOutline width="18" height="18" class="shrink-0 text-danger" />
              <h2 class="text-2xl font-medium text-fg">{selected.name}</h2>
            </div>
            <div class="overflow-hidden rounded border border-danger/40 bg-danger/5">
              <div class="border-b border-danger/30 px-3 py-2">
                <div class="text-lg font-medium text-danger">
                  {selected.source === 'config' ? 'config.yaml' : 'bench.json'} couldn't be loaded — {errorEntries.length}
                  issue{errorEntries.length === 1 ? '' : 's'}
                </div>
                <p class="mt-0.5 text-base text-fg-muted">
                  {selected.source === 'config'
                    ? 'Fix these fields in the instrument configuration before it can be opened.'
                    : 'The saved bench no longer matches the current schema. Fix or delete bench.json to recover.'}
                </p>
              </div>
              {#if errorEntries.length === 0}
                <p class="px-3 py-2 text-lg text-fg-muted">No further details were reported.</p>
              {:else}
                <ul class="divide-y divide-border/40">
                  {#each errorEntries as [location, message] (location)}
                    <li class="flex flex-col gap-0.5 px-3 py-2">
                      <span class="font-mono text-base break-all text-fg-muted">
                        {location === '' ? 'file' : location === '<model>' ? 'model' : location}
                      </span>
                      <span class="text-lg text-danger">{message}</span>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {:else}
          <InstrumentInspector hal={selected.hal} bench={selected.bench} />
        {/if}
      {:else}
        <div class="flex h-full items-center justify-center">
          <p class="text-lg text-fg-muted/60">Select an instrument or template</p>
        </div>
      {/if}
    </div>
  </div>

  <!-- Logs -->
  <LogViewer logs={app.logs} class="flex-1 border-l border-border bg-canvas" />
</div>

<Dialog.Root bind:open={dialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Create Instrument</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        From template <span class="font-medium text-fg">{dialogTemplate}</span>.
      </p>
      <Field label="Instance Name" id="instance-name">
        <TextInput bind:value={dialogName} id="instance-name" align="left" placeholder={dialogTemplate} />
      </Field>
    </div>

    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (dialogOpen = false)}>Cancel</Button>
      <Button variant="success" disabled={app.busy} onclick={createFromTemplate}>
        {app.busy ? 'Creating…' : 'Create'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
