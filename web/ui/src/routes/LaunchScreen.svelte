<script lang="ts">
  import { Pane, PaneGroup } from 'paneforge';
  import { toast } from 'svelte-sonner';

  import { wavelengthToColor } from '$lib/colors.svelte';
  import { AlertCircleOutline, Cog, PanelLeft } from '$lib/icons';
  import { Button, Dialog, Field, JsonView, TextInput } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import {
    ApiError,
    type HALConfig,
    type InstrumentConfig,
    type InstrumentDefaults,
    type InstrumentInspection,
    isLoaded,
    type Violation,
    type VoxelApp
  } from '$lib/model';
  import { themes } from '$lib/themes';
  import { cn, createPaneSize, sanitizeString } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  interface Props {
    app: VoxelApp;
  }

  type Selection = { kind: 'instrument'; name: string } | { kind: 'template'; name: string };
  type ContentView = 'overview' | 'configuration';
  type Selected = {
    name: string;
    kind: Selection['kind'];
    config: InstrumentConfig | null;
    bench: InstrumentDefaults | null;
    stateSource: 'bench' | 'default' | null;
    errorSource: 'config' | 'bench' | null;
    errors: Violation[];
  };

  type LaunchFailure = {
    selectionId: string;
    violations: Violation[];
  };

  type Failure = {
    title: string;
    description: string;
    source: 'config' | 'bench' | 'startup';
    violations: Violation[];
  };

  const { app }: Props = $props();

  let selection = $state<Selection | null>(null);
  let contentView = $state<ContentView>('overview');
  let sidebarOpen = $state(true);
  let launchFailure = $state<LaunchFailure | null>(null);
  let splitEl = $state<HTMLElement | null>(null);

  const workspacePane = createPaneSize(() => splitEl, {
    min: 54,
    default: 54,
    fallback: { min: 45 }
  });
  const logsPane = createPaneSize(() => splitEl, {
    min: 54,
    fallback: { min: 30, default: 40, max: 60 }
  });

  // Create-from-template dialog state.
  let createDialogOpen = $state(false);
  let dialogTemplate = $state('');
  let dialogName = $state('');

  // Archive-bench dialog state.
  let archiveBenchDialogOpen = $state(false);
  let archiveBenchInstrument = $state('');

  const instrumentEntries = $derived(Object.entries(app.discovery.instruments));
  const templateEntries = $derived(Object.entries(app.discovery.templates));
  const selectedId = $derived(selection ? selectionId(selection) : null);

  const selected = $derived.by((): Selected | null => {
    if (!selection) return null;

    if (selection.kind === 'template') {
      const config = app.discovery.templates[selection.name];
      if (!config) return null;
      return {
        name: selection.name,
        kind: 'template',
        config,
        bench: config.default,
        stateSource: 'default',
        errorSource: null,
        errors: []
      };
    }

    const info = app.discovery.instruments[selection.name];
    if (!info) return null;
    const config = isLoaded(info.config) ? info.config.value : null;
    const configErrors = violationsFor(info, 'config');
    if (config === null || configErrors.length > 0) {
      return {
        name: selection.name,
        kind: 'instrument',
        config,
        bench: null,
        stateSource: null,
        errorSource: 'config',
        errors: configErrors
      };
    }

    const errors = violationsFor(info, 'bench');
    const state = isLoaded(info.state) ? info.state.value : null;
    return {
      name: selection.name,
      kind: 'instrument',
      config,
      bench: errors.length > 0 ? config.default : (state ?? config.default),
      stateSource: errors.length > 0 || state === null ? 'default' : 'bench',
      errorSource: errors.length > 0 ? 'bench' : null,
      errors
    };
  });

  const action = $derived.by(() => {
    if (!selected?.config || selected.errorSource) return null;
    return selected.kind === 'template'
      ? { label: 'Create', onclick: () => openCreateDialog(selected.name) }
      : { label: 'Open', onclick: () => openInstrument(selected.name) };
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

    if (launchFailure && launchFailure.selectionId === selectedId) {
      return {
        title: `Unable to open ${selected?.name ? sanitizeString(selected.name) : 'instrument'}`,
        description: 'Hardware startup did not complete. Review the reported issues and retry when they are resolved.',
        source: 'startup',
        violations: launchFailure.violations
      };
    }

    return null;
  });

  $effect(() => {
    if (selection !== null) return;
    const last = app.lastInstrument;
    if (last && last in app.discovery.instruments) {
      selection = { kind: 'instrument', name: last };
    } else if (instrumentEntries.length > 0) {
      selection = { kind: 'instrument', name: instrumentEntries[0][0] };
    } else if (templateEntries.length > 0) {
      selection = { kind: 'template', name: templateEntries[0][0] };
    }
  });

  $effect(() => {
    if (app.client.state === 'connected') app.refresh();
  });

  function selectionId(value: Selection): string {
    return `${value.kind}:${value.name}`;
  }

  function select(next: Selection): void {
    selection = next;
    contentView = 'overview';
    launchFailure = null;
  }

  function isSelected(kind: Selection['kind'], name: string): boolean {
    return selection?.kind === kind && selection.name === name;
  }

  function violationsFor(info: InstrumentInspection, source: 'config' | 'bench'): Violation[] {
    return info.violations.filter((violation) => violation.loc?.[0] === source);
  }

  function hasError(info: InstrumentInspection): boolean {
    return info.violations.length > 0;
  }

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

  async function openInstrument(name: string): Promise<void> {
    const id = selectionId({ kind: 'instrument', name });
    launchFailure = null;
    try {
      await app.launch(name);
    } catch (error) {
      launchFailure = { selectionId: id, violations: parseViolations(error) };
    }
  }

  function openCreateDialog(template: string): void {
    dialogTemplate = template;
    dialogName = template;
    createDialogOpen = true;
  }

  async function createFromTemplate(): Promise<void> {
    const name = sanitize(dialogName) || dialogTemplate;
    const id = selectionId({ kind: 'template', name: dialogTemplate });
    launchFailure = null;
    try {
      await app.launchTemplate(dialogTemplate, name);
      createDialogOpen = false;
    } catch (error) {
      createDialogOpen = false;
      launchFailure = { selectionId: id, violations: parseViolations(error) };
    }
  }

  function openArchiveBenchDialog(name: string): void {
    archiveBenchInstrument = name;
    archiveBenchDialogOpen = true;
  }

  async function submitArchiveBench(): Promise<void> {
    try {
      await app.archiveBench(archiveBenchInstrument);
      archiveBenchDialogOpen = false;
      launchFailure = null;
    } catch {
      if (app.error) toast.error(app.error);
    }
  }

  function sanitize(value: string): string {
    return value.trim().toLowerCase().replace(/\s+/g, '-');
  }

  function deviceCount(hal: HALConfig): number {
    return (
      Object.keys(hal.devices).length +
      Object.values(hal.nodes).reduce((count, node) => count + Object.keys(node.devices).length, 0)
    );
  }

  function violationLocation(violation: Violation): string {
    if (!violation.loc || violation.loc.length === 0) return '';
    return violation.loc.join('.');
  }
</script>

<div class="h-screen w-full">
  <PaneGroup direction="horizontal" bind:ref={splitEl} autoSaveId="launch:logs" class="bg-canvas">
    <Pane {...workspacePane} class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-surface/60">
      <!-- Workspace header -->
      <header class="flex h-15 shrink-0 items-center gap-2 border-b border-border bg-surface px-4">
        <VoxelLogo class="size-ui-md shrink-0" />
        <span class="min-w-0 flex-1 truncate text-4xl font-light tracking-wider text-fg uppercase">Voxel</span>
        <button
          title="Appearance"
          aria-label="Appearance"
          onclick={() => (themes.pickerOpen = true)}
          class="flex size-7 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
        >
          <Cog width="24" height="24" />
        </button>
      </header>

      <div class="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <!-- Catalog -->
        <aside
          class={cn(
            'shrink-0 overflow-hidden border-r bg-surface transition-[width,border-color] duration-200 ease-out',
            sidebarOpen ? 'w-56 border-border' : 'w-0 border-transparent'
          )}
          aria-hidden={!sidebarOpen}
          inert={!sidebarOpen}
        >
          <div class="flex h-full w-56 flex-col overflow-hidden">
            <div class="min-h-0 flex-1 overflow-y-auto">
              <section>
                <div class="flex h-12 shrink-0 items-center gap-2 px-3">
                  <span class="min-w-0 flex-1 text-sm tracking-wide text-fg-faint uppercase">Instruments</span>
                  <button
                    class="flex size-7 shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                    title="Collapse instrument list"
                    aria-label="Collapse instrument list"
                    onclick={() => (sidebarOpen = false)}
                  >
                    <PanelLeft width="16" height="16" />
                  </button>
                </div>
                <div class="flex flex-col gap-0.5 px-2">
                  {#each instrumentEntries as [name, info] (name)}
                    <button
                      class={cn(
                        'flex w-full items-center gap-2 rounded px-2 py-1 text-left transition-colors',
                        isSelected('instrument', name)
                          ? 'bg-element-selected text-fg'
                          : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                      )}
                      onclick={() => select({ kind: 'instrument', name })}
                    >
                      <span class="min-w-0 flex-1 truncate">{sanitizeString(name)}</span>
                      {#if hasError(info)}
                        <span class="size-1.5 shrink-0 rounded-full bg-danger" title="Failed validation"></span>
                      {/if}
                    </button>
                  {/each}
                  {#if instrumentEntries.length === 0}
                    <p class="px-2 py-1 text-fg-faint">No instruments</p>
                  {/if}
                </div>
              </section>

              {#if templateEntries.length > 0}
                <div class="mx-3 mt-3 mb-2 h-px bg-border"></div>
                <section>
                  <div class="mb-1 px-3 text-sm tracking-wide text-fg-faint uppercase">Templates</div>
                  <div class="flex flex-col gap-0.5 px-2">
                    {#each templateEntries as [name] (name)}
                      <button
                        class={cn(
                          'w-full truncate rounded px-2 py-1 text-left transition-colors',
                          isSelected('template', name)
                            ? 'bg-element-selected text-fg'
                            : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                        )}
                        onclick={() => select({ kind: 'template', name })}
                      >
                        {sanitizeString(name)}
                      </button>
                    {/each}
                  </div>
                </section>
              {/if}
            </div>
          </div>
        </aside>

        <!-- Selected instrument -->
        <main class="flex min-h-0 min-w-0 flex-1 flex-col">
          <header class="shrink-0 border-b border-border">
            <div class="flex min-h-12 items-center gap-3 px-4 py-2">
              {#if !sidebarOpen}
                <button
                  class="flex size-7 shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                  title="Expand instrument list"
                  aria-label="Expand instrument list"
                  onclick={() => (sidebarOpen = true)}
                >
                  <PanelLeft width="16" height="16" />
                </button>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <h1 class="truncate text-2xl font-medium text-fg">
                    {selected ? sanitizeString(selected.name) : 'Select an instrument'}
                  </h1>
                  {#if selected}
                    <span class="shrink-0 rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">
                      {selected.kind === 'template' ? 'Template' : 'Instrument'}
                    </span>
                  {/if}
                </div>
              </div>
              {#if action}
                <Button variant="success" size="sm" disabled={app.busy} onclick={action.onclick}>
                  {app.busy ? `${action.label}…` : action.label}
                </Button>
              {/if}
            </div>

            {#if selected}
              <nav class="flex gap-1 px-3">
                <button
                  class={cn(
                    'border-b-2 px-2 py-1.5 transition-colors',
                    contentView === 'overview' ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'
                  )}
                  onclick={() => (contentView = 'overview')}
                >
                  Overview
                </button>
                <button
                  class={cn(
                    'border-b-2 px-2 py-1.5 transition-colors',
                    contentView === 'configuration'
                      ? 'border-fg text-fg'
                      : 'border-transparent text-fg-muted hover:text-fg'
                  )}
                  onclick={() => (contentView = 'configuration')}
                >
                  Configuration
                </button>
              </nav>
            {/if}
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto">
            {#if selected}
              {#if failure}
                <div class="px-4 pt-4">
                  <section class="overflow-hidden rounded-lg border border-danger/40 bg-danger/5">
                    <div class="flex items-start gap-3 border-b border-danger/25 px-3 py-2.5">
                      <AlertCircleOutline width="18" height="18" class="mt-0.5 shrink-0 text-danger" />
                      <div class="min-w-0 flex-1">
                        <h2 class="text-lg font-medium text-danger">{failure.title}</h2>
                        <p class="mt-0.5 text-fg-muted">{failure.description}</p>
                      </div>
                      <div class="flex shrink-0 items-center gap-2">
                        {#if failure.source === 'bench' && selected.kind === 'instrument'}
                          <Button variant="outline" size="xs" onclick={() => openArchiveBenchDialog(selected.name)}>
                            Archive bench…
                          </Button>
                        {:else if failure.source === 'startup' && selected.kind === 'instrument'}
                          <Button
                            variant="outline"
                            size="xs"
                            disabled={app.busy}
                            onclick={() => openInstrument(selected.name)}
                          >
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
                              <span class="font-mono text-sm break-all text-fg-muted"
                                >{violationLocation(violation)}</span
                              >
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

              {#if contentView === 'overview'}
                {@render overview(selected)}
              {:else}
                {@render configuration(selected)}
              {/if}
            {:else}
              <div class="flex h-full items-center justify-center p-8">
                <p class="text-lg text-fg-muted">Select an instrument or template</p>
              </div>
            {/if}
          </div>
        </main>
      </div>
    </Pane>

    <PaneDivider direction="vertical" />

    <Pane {...logsPane} class="min-h-0 min-w-0 bg-canvas">
      <LogViewer logs={app.logs} />
    </Pane>
  </PaneGroup>
</div>

{#snippet overview(value: Selected)}
  {#if value.config}
    {@const hal = value.config.hal}
    {@const bench = value.bench ?? value.config.default}
    <div class="space-y-6 p-4">
      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Summary</h2>
        <dl class="grid max-w-3xl grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
          <dt class="text-fg-muted">Devices</dt>
          <dd class="font-mono text-fg">{deviceCount(hal)}</dd>
          <dt class="text-fg-muted">Nodes</dt>
          <dd class="font-mono text-fg">{Object.keys(hal.nodes).length}</dd>
          <dt class="text-fg-muted">Detection paths</dt>
          <dd class="font-mono text-fg">{Object.keys(hal.detection).length}</dd>
          <dt class="text-fg-muted">Illumination paths</dt>
          <dd class="font-mono text-fg">{Object.keys(hal.illumination).length}</dd>
          <dt class="text-fg-muted">Profiles</dt>
          <dd class="font-mono text-fg">{Object.keys(bench.imaging.profiles).length}</dd>
          <dt class="text-fg-muted">Channels</dt>
          <dd class="font-mono text-fg">{Object.keys(bench.imaging.channels).length}</dd>
        </dl>
      </section>

      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Profiles</h2>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {#each Object.entries(bench.imaging.profiles) as [profileId, profile] (profileId)}
            <article class="rounded-lg border bg-card p-3 shadow-sm">
              <h3 class="truncate text-lg font-medium text-fg">{profile.label ?? sanitizeString(profileId)}</h3>
              {#if profile.desc}
                <p class="mt-1 line-clamp-2 text-fg-muted">{profile.desc}</p>
              {/if}
              <div class="mt-2 flex flex-wrap gap-1.5">
                {#each profile.channels as channelId (channelId)}
                  {@const channel = bench.imaging.channels[channelId]}
                  <span class="flex items-center gap-1 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">
                    {#if channel?.emission}
                      <span
                        class="size-1.5 rounded-full"
                        style="background-color: {wavelengthToColor(channel.emission)}"
                      ></span>
                    {/if}
                    {channel?.label ?? sanitizeString(channelId)}
                  </span>
                {/each}
              </div>
            </article>
          {/each}
        </div>
      </section>

      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Channels</h2>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {#each Object.entries(bench.imaging.channels) as [channelId, channel] (channelId)}
            <article class="rounded-lg border bg-card p-3 shadow-sm">
              <div class="flex items-center gap-2">
                {#if channel.emission}
                  <span
                    class="size-2.5 shrink-0 rounded-full"
                    style="background-color: {wavelengthToColor(channel.emission)}"
                  ></span>
                {/if}
                <h3 class="truncate text-lg font-medium text-fg">{channel.label ?? sanitizeString(channelId)}</h3>
              </div>
              <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                <dt class="text-fg-muted">Detection</dt>
                <dd class="truncate text-right text-fg">{channel.detection}</dd>
                <dt class="text-fg-muted">Illumination</dt>
                <dd class="truncate text-right text-fg">{channel.illumination}</dd>
              </dl>
            </article>
          {/each}
        </div>
      </section>
    </div>
  {:else}
    <div class="p-4 text-fg-muted">The configuration could not be parsed.</div>
  {/if}
{/snippet}

{#snippet configuration(value: Selected)}
  <div class="space-y-6 p-4">
    {#if value.bench}
      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">
          {value.stateSource === 'default' ? 'Configured Default' : 'Bench'}
        </h2>
        <JsonView data={value.bench} expandDepth={1} />
      </section>
    {/if}
    {#if value.config}
      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Hardware</h2>
        <JsonView data={value.config.hal} expandDepth={1} />
      </section>
    {:else}
      <p class="text-fg-muted">The configuration could not be parsed.</p>
    {/if}
  </div>
{/snippet}

<Dialog.Root bind:open={createDialogOpen}>
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
      <Button variant="outline" onclick={() => (createDialogOpen = false)}>Cancel</Button>
      <Button variant="success" disabled={app.busy} onclick={createFromTemplate}>
        {app.busy ? 'Creating…' : 'Create'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={archiveBenchDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Archive Bench</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        Archive <span class="font-medium text-fg">{sanitizeString(archiveBenchInstrument)}</span>'s current bench so it
        reopens with its configured defaults. The archived state is retained as
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
