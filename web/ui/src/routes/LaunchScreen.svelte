<script lang="ts">
  import { Collapsible } from 'bits-ui';
  import { toast } from 'svelte-sonner';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import type { App } from '$lib/app.svelte';
  import { Clipboard, Cog, EllipsisVertical, FolderOpenOutline, GitFork, LucideChevronRight, Plus } from '$lib/icons';
  import { Button, Checkbox, Dialog, DropdownMenu, Field, Select, TextInput } from '$lib/kit';
  import MetadataFields from '$lib/metadata/MetadataFields.svelte';
  import type { DataRoot, SessionListing, TemplateInfo } from '$lib/protocol/app';
  import { themes } from '$lib/themes';
  import type { JsonSchema } from '$lib/types';
  import { sanitizeString } from '$lib/utils';

  import LogViewer from './LogViewer.svelte';
  import VoxelLogo from './VoxelLogo.svelte';

  const { app }: { app: App } = $props();

  let sessions = $state<SessionListing[]>([]);
  let templates = $state<TemplateInfo[]>([]);
  let dataRoots = $state<DataRoot[]>([]);
  let loadingSessions = $state(false);
  let error = $state<string | null>(null);
  let metadataSchemas = $state<Record<string, string>>({});
  let metadataSchema = $state<JsonSchema | null>(null);

  // Dialog state
  let dialogOpen = $state(false);
  let forkTarget = $state<SessionListing | null>(null);

  // Unified form state
  let formName = $state('');
  let formDescription = $state('');
  let formTemplate = $state('');
  let formDataRoot = $state('');
  let formMetaTarget = $state('');
  let formMetadata = $state<Record<string, unknown>>({});
  let formClearStacks = $state(true);
  let formSubmitting = $state(false);

  const appStatus = $derived(app.status?.status);
  const isLaunching = $derived(appStatus === 'launching');
  const connectionState = $derived(app.client.state);
  const logs = $derived(app.logs);

  // Derived
  const isFork = $derived(forkTarget !== null);
  const forkSourceName = $derived(forkTarget?.config?.info.name || forkTarget?.uid || '');
  const formValid = $derived(isFork ? formName.trim().length > 0 : formTemplate.length > 0);
  const templateOptions = $derived(templates.map((t) => ({ value: t.name, label: t.rig_name || t.name })));
  const dataRootOptions = $derived(dataRoots.map((r) => ({ value: r.name, label: r.label ?? r.name })));

  // ── Effects ──

  $effect(() => {
    if (connectionState === 'connected') {
      loadAllSessions();
      app
        .fetchTemplates()
        .then((t) => (templates = t))
        .catch(console.warn);
      app
        .fetchDataRoots()
        .then((r) => (dataRoots = r))
        .catch(console.warn);
      app
        .fetchMetadataSchemas()
        .then((t) => (metadataSchemas = t))
        .catch(console.warn);
    }
  });

  // Reset form when dialog opens
  $effect(() => {
    if (dialogOpen) {
      formSubmitting = false;
      formDataRoot = dataRoots.find((r) => r.default)?.name ?? dataRoots[0]?.name ?? '';
      const keys = Object.keys(metadataSchemas);
      formMetaTarget = keys.length > 0 ? keys[0] : '';
      if (keys.length > 0) handleMetadataSchemaChanged(metadataSchemas[keys[0]]);
      formMetadata = {};

      if (forkTarget) {
        // Fork mode: pre-fill from source
        formName = (forkTarget.config?.info.name || forkTarget.uid) + '-fork';
        formDescription = forkTarget.config?.info.description ?? '';
        formTemplate = '';
        formClearStacks = true;
      } else {
        // Create mode
        formName = '';
        formDescription = '';
        formTemplate = templates.length > 0 ? templates[0].name : '';
        formClearStacks = true;
      }
    }
  });

  // Reset metadata values when schema changes
  $effect(() => {
    if (!metadataSchema) {
      formMetadata = {};
      return;
    }
    const values: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(metadataSchema.properties)) {
      if (prop.default !== undefined) values[key] = prop.default;
      else if (prop.type === 'array') values[key] = [''];
      else if (prop.type === 'string') values[key] = '';
      else if (prop.type === 'number' || prop.type === 'integer') values[key] = 0;
    }
    formMetadata = values;
  });

  // ── Handlers ──

  async function loadAllSessions() {
    loadingSessions = true;
    error = null;
    try {
      sessions = await app.fetchSessions();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load sessions';
      sessions = [];
    } finally {
      loadingSessions = false;
    }
  }

  async function handleMetadataSchemaChanged(target: string) {
    try {
      metadataSchema = await app.fetchMetadataSchema(target);
    } catch (e) {
      console.warn('[LaunchScreen] Failed to fetch metadata schema:', e);
      metadataSchema = null;
    }
  }

  async function handleSubmitSession() {
    if (!formValid || formSubmitting) return;
    formSubmitting = true;
    error = null;
    try {
      const name = formName.trim().toLowerCase().replace(/\s+/g, '-');
      if (forkTarget) {
        const sourceUid = forkTarget.uid;
        await app.forkSession(sourceUid, {
          name,
          description: formDescription,
          clearStacks: formClearStacks
        });
      } else {
        await app.createSession(formTemplate, {
          dataRoot: formDataRoot || undefined,
          name,
          description: formDescription
        });
      }
      dialogOpen = false;
      goto(resolve('/scout'));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to create session';
    } finally {
      formSubmitting = false;
    }
  }

  async function handleResumeSession(session: SessionListing) {
    error = null;
    try {
      const uid = session.uid;
      await app.resumeSession(uid);
      goto(resolve('/scout'));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to resume session';
    }
  }

  function openForkDialog(session: SessionListing) {
    forkTarget = session;
    dialogOpen = true;
  }

  function openNewSessionDialog() {
    forkTarget = null;
    dialogOpen = true;
  }

  // ── Helpers ──

  function formatRelativeTime(isoString: string): string {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function formatDate(isoString: string): string {
    if (!isoString) return '';
    return new Date(isoString).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  async function copyPath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      toast.success('Copied to clipboard');
    } catch {
      toast.error('Failed to copy');
    }
  }

  function handleFormMetaTargetChange(key: string) {
    const target = metadataSchemas[key];
    if (target) handleMetadataSchemaChanged(target);
  }

  function setFormMetaValue(key: string, val: unknown) {
    formMetadata = { ...formMetadata, [key]: val };
  }
</script>

<!-- ── Session Card Snippet ── -->
{#snippet sessionCard(session: SessionListing)}
  {@const info = session.config?.info}
  {@const hasError = session.errors.length > 0}

  <div
    class={hasError
      ? 'rounded border border-danger/30 bg-danger/5 px-3 py-2.5'
      : 'rounded border border-border bg-card px-3 py-2.5'}
  >
    {#if hasError}
      <div class="flex w-full items-center gap-2">
        <span class="min-w-0 flex-1 truncate text-sm font-medium text-fg">
          {info?.name || session.uid}
        </span>
      </div>
      <div class="mt-2 text-xs text-danger">{session.errors[0]}</div>
    {:else}
      <Collapsible.Root>
        <div class="flex w-full items-center gap-2">
          <Collapsible.Trigger
            class="flex min-w-0 flex-1 items-center gap-1 text-sm font-medium text-fg hover:text-fg [&[data-state=open]>svg]:rotate-90"
          >
            <LucideChevronRight
              width="12"
              height="12"
              class="shrink-0 text-fg-muted transition-transform duration-200"
            />
            <span class="truncate">{info?.name || session.uid}</span>
          </Collapsible.Trigger>

          {#if info?.last_opened}
            <span class="shrink-0 text-xs text-fg-muted/60">
              {formatRelativeTime(info.last_opened)}
            </span>
          {/if}

          <div class="flex items-center gap-0.5">
            <Button variant="ghost" size="xs" onclick={() => handleResumeSession(session)}>Resume</Button>

            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                {#snippet child({ props })}
                  <button {...props} class="text-fg-muted/40 hover:text-fg-muted">
                    <EllipsisVertical width="14" height="14" />
                  </button>
                {/snippet}
              </DropdownMenu.Trigger>
              <DropdownMenu.Content
                align="end"
                side="bottom"
                sideOffset={16}
                alignOffset={-12}
                class="min-w-40 **:data-[slot=dropdown-menu-item]:py-1"
              >
                <DropdownMenu.Item onclick={() => openForkDialog(session)}>
                  <GitFork width="12" height="12" />
                  Fork
                </DropdownMenu.Item>
                {#if session.location}
                  <DropdownMenu.Separator />
                  <DropdownMenu.Item onclick={() => copyPath(session.location!)}>
                    <Clipboard width="12" height="12" />
                    Copy location
                  </DropdownMenu.Item>
                {/if}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          </div>
        </div>

        <Collapsible.Content
          class="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down"
        >
          <div class="mt-2 space-y-1 border-t border-border/50 pt-1.5 pl-5 text-xs text-fg-muted">
            <div class="grid grid-cols-[4rem_1fr] items-center gap-x-3 *:h-5 [&>*:nth-child(odd)]:text-fg-muted/80">
              <span>Rig</span>
              <span>{session.config?.rig.name ?? ''}</span>
              {#if info?.source}
                <span>Source</span>
                <span>{info.source}</span>
              {/if}
              {#if info?.description}
                <span>Description</span>
                <span>{info.description}</span>
              {/if}
              {#if info?.collection}
                <span>Collection</span>
                <span>{info.collection}</span>
              {/if}
              {#if session.location}
                <span>Location</span>
                <div class="flex min-w-0 items-center gap-1">
                  <span class="min-w-0 truncate">{session.location}</span>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onclick={() => copyPath(session.location!)}
                    title="Copy location"
                  >
                    <Clipboard width="10" height="10" />
                  </Button>
                </div>
              {/if}
            </div>

            <div class="flex items-center gap-2 py-2">
              {#if info?.created_at}
                <span>Created {formatDate(info.created_at)}</span>
                <span>&middot;</span>
              {/if}
              {#if info?.last_opened}
                <span>Last opened {formatDate(info.last_opened)}</span>
              {/if}
              {#if info && info.open_count > 0}
                <span>&middot;</span>
                <span>Opened {info.open_count} {info.open_count === 1 ? 'time' : 'times'}</span>
              {/if}
            </div>
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    {/if}
  </div>
{/snippet}

<!-- ═══════════════════════════════════════════ -->
<!-- Main Layout                                -->
<!-- ═══════════════════════════════════════════ -->

<div class="flex h-screen w-full bg-canvas">
  <!-- Left panel -->
  <div class="flex w-180 shrink-0 flex-col border-r border-border">
    <!-- Header -->
    <div class="shrink-0 p-4 pb-0">
      <div class="mb-4 flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <VoxelLogo class="h-8 w-8" />
            <h1 class="text-2xl font-light text-fg uppercase">Voxel</h1>
          </div>
          <button
            title="Appearance"
            onclick={() => (themes.pickerOpen = true)}
            class="flex items-center rounded p-1 text-fg-muted transition-colors hover:text-fg"
          >
            <Cog width="16" height="16" />
          </button>
        </div>
        <!-- <p class="text-sm text-fg-muted">Light sheet microscopy</p> -->
      </div>

      {#if error}
        <div class="mb-4 rounded border border-danger/50 bg-danger/10 px-4 py-3 text-base text-danger">
          {error}
        </div>
      {/if}
    </div>

    {#if isLaunching}
      <div class="flex flex-1 items-center justify-center gap-2">
        <div class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
        <p class="text-sm text-fg-muted">Starting session&hellip;</p>
      </div>
    {:else}
      <!-- Toolbar -->
      <div class="flex items-center gap-2 px-4 py-3">
        <Button variant="ghost" size="sm" onclick={openNewSessionDialog}>
          <Plus width="14" height="14" />
          New Session
        </Button>
        <span class="flex-1"></span>
      </div>

      <!-- Session list -->
      <div class="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        {#if loadingSessions}
          <div class="flex items-center justify-center rounded border border-border bg-card py-12">
            <div class="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-fg-muted"></div>
            <span class="ml-3 text-base text-fg-muted">Loading sessions...</span>
          </div>
        {:else if sessions.length === 0}
          <div
            class="flex flex-col items-center justify-center rounded border border-dashed border-border bg-card py-10"
          >
            <FolderOpenOutline width="32" height="32" class="text-fg-muted/50" />
            <p class="mt-2 text-base text-fg-muted">No recent sessions</p>
            <p class="text-sm text-fg-muted/60">Create a new session to get started</p>
          </div>
        {:else}
          <div class="space-y-2">
            {#each sessions as session (session.uid)}
              {@render sessionCard(session)}
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Right panel: logs -->
  <div class="flex flex-1 flex-col bg-card p-4">
    <LogViewer {logs} onClear={() => app.clearLogs()} />
  </div>
</div>

<!-- ═══════════════════════════════════════════ -->
<!-- New Session Dialog                         -->
<!-- ═══════════════════════════════════════════ -->

<Dialog.Root bind:open={dialogOpen}>
  <Dialog.Content size="xl">
    <Dialog.Header>
      {#if isFork}
        <Dialog.Title>Forking: {forkSourceName}</Dialog.Title>
      {:else}
        <Dialog.Title>New Session</Dialog.Title>
      {/if}
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4">
      <div class="grid grid-cols-2 gap-4">
        {#if !isFork}
          <Field label="Template">
            <Select options={templateOptions} bind:value={formTemplate} />
          </Field>
        {/if}

        <Field label="Data Root">
          <Select options={dataRootOptions} bind:value={formDataRoot} />
        </Field>

        <Field label="Session Name" id="form-name">
          <TextInput bind:value={formName} id="form-name" align="left" placeholder="Auto-generated if empty" />
        </Field>

        <Field label="Description">
          <TextInput bind:value={formDescription} align="left" placeholder="" />
        </Field>
      </div>

      <div class="flex flex-col gap-2">
        <div class="col-span-full my-1 flex items-center gap-3">
          <span class="shrink-0 text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Metadata</span>
          <hr class="flex-1 border-border" />
        </div>

        {#if Object.keys(metadataSchemas).length > 0}
          <div class="col-span-full grid grid-cols-[10rem_1fr] items-center gap-x-3">
            <div class="text-xs text-fg-muted">Schema</div>
            <Select
              options={Object.keys(metadataSchemas).map((k) => ({ value: k, label: sanitizeString(k) }))}
              bind:value={formMetaTarget}
              onchange={handleFormMetaTargetChange}
              size="sm"
            />
          </div>
        {/if}

        {#if metadataSchema}
          <div class="col-span-full grid grid-cols-[10rem_1fr] items-start gap-x-3 gap-y-2 pb-2">
            <MetadataFields schema={metadataSchema} values={formMetadata} onChange={setFormMetaValue} size="sm">
              <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
              {#snippet field(key, _prop, input)}
                <div class="pt-1 text-xs text-fg-muted">{sanitizeString(key)}</div>
                <div>{@render input()}</div>
              {/snippet}
            </MetadataFields>
          </div>
        {/if}
      </div>
    </div>
    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex items-center gap-2">
        <Checkbox bind:checked={formClearStacks} disabled={!isFork} />
        <span class="text-xs text-fg-muted">Clear stacks</span>
      </div>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (dialogOpen = false)}>Cancel</Button>
      <Button variant="success" onclick={handleSubmitSession} disabled={!formValid || formSubmitting}>
        {formSubmitting ? 'Creating...' : isFork ? 'Create Fork' : 'Create Session'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
