<script lang="ts">
  import type { App } from '$lib/main';
  import type { SessionListing, SessionRoot, JsonSchema } from '$lib/main';
  import AppMenu from './AppMenu.svelte';
  import LogViewer from '$lib/ui/LogViewer.svelte';
  import MetadataFields from '$lib/ui/MetadataFields.svelte';
  import { Collapsible } from 'bits-ui';
  import { Button, Checkbox, Dialog, DropdownMenu, Field, Select, TextInput } from '$lib/ui/kit';
  import {
    Plus,
    FolderOpenOutline,
    Star,
    StarOff,
    Archive,
    GitFork,
    Clipboard,
    LucideChevronRight,
    EllipsisVertical
  } from '$lib/icons';
  import { sanitizeString } from '$lib/utils';
  import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { toast } from 'svelte-sonner';

  const { app }: { app: App } = $props();

  let sessions = $state<SessionListing[]>([]);
  let loadingSessions = $state(false);
  let error = $state<string | null>(null);
  let metadataTargets = $state<Record<string, string>>({});
  let metadataSchema = $state<JsonSchema | null>(null);

  // Dialog state
  let newSessionOpen = $state(false);
  let forkSessionOpen = $state(false);
  let forkTarget = $state<SessionListing | null>(null);

  // New session form state
  let nsName = $state('');
  let nsRoot = $state('');
  let nsRig = $state('');
  let nsMetaTarget = $state('');
  let nsMetadata = $state<Record<string, unknown>>({});
  let nsSubmitting = $state(false);

  // Fork form state
  let fkName = $state('');
  let fkDescription = $state('');
  let fkRoot = $state('');
  let fkClearStacks = $state(false);
  let fkSubmitting = $state(false);

  const roots = $derived(app.status?.roots ?? []);
  const rigs = $derived(app.status?.rigs ?? []);
  const phase = $derived(app.status?.phase);
  const isIdle = $derived(phase === 'idle');
  const isLaunching = $derived(phase === 'launching');
  const connectionState = $derived(app.client.connectionState);
  const logs = $derived(app.logs);
  const rootOptions = $derived(roots.map((r: SessionRoot) => ({ value: r.name, label: r.label ?? r.name })));

  // New session form derived
  const nsValid = $derived(nsRoot.length > 0 && nsRig.length > 0);

  // Fork form derived
  const fkSourceName = $derived(forkTarget?.config?.info.name || forkTarget?.directory.name || '');

  const fkValid = $derived(fkRoot.length > 0 && fkName.trim().length > 0);

  // ── Effects ──

  $effect(() => {
    if (roots.length > 0) loadAllSessions();
  });

  $effect(() => {
    app
      .fetchMetadataTargets()
      .then((targets) => {
        metadataTargets = targets;
      })
      .catch((e) => console.warn('[LaunchScreen] Failed to fetch metadata targets:', e));
  });

  // Reset new session form when dialog opens
  $effect(() => {
    if (newSessionOpen) {
      nsName = '';
      nsRoot = roots.length > 0 ? roots[0].name : '';
      nsRig = rigs.length > 0 ? rigs[0] : '';
      const keys = Object.keys(metadataTargets);
      nsMetaTarget = keys.length > 0 ? keys[0] : '';
      if (keys.length > 0) handleMetadataTargetChanged(metadataTargets[keys[0]]);
      nsMetadata = {};
    }
  });

  // Reset metadata values when schema changes
  $effect(() => {
    if (!metadataSchema) {
      nsMetadata = {};
      return;
    }
    const values: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(metadataSchema.properties)) {
      if (prop.default !== undefined) values[key] = prop.default;
      else if (prop.type === 'array') values[key] = [''];
      else if (prop.type === 'string') values[key] = '';
      else if (prop.type === 'number' || prop.type === 'integer') values[key] = 0;
    }
    nsMetadata = values;
  });

  // Populate fork form when target changes
  $effect(() => {
    if (forkTarget) {
      fkName = (forkTarget.config?.info.name || forkTarget.directory.name) + '-fork';
      fkDescription = forkTarget.config?.info.description ?? '';
      fkRoot = forkTarget.directory.root_name;
      fkClearStacks = false;
    }
  });

  // ── Handlers ──

  async function loadAllSessions() {
    loadingSessions = true;
    error = null;
    try {
      const allSessions = await Promise.all(roots.map((root: SessionRoot) => app.fetchSessions(root.name)));
      sessions = allSessions
        .flat()
        .sort((a, b) => new Date(b.directory.modified).getTime() - new Date(a.directory.modified).getTime());
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load sessions';
      sessions = [];
    } finally {
      loadingSessions = false;
    }
  }

  async function handleMetadataTargetChanged(target: string) {
    try {
      metadataSchema = await app.fetchMetadataSchema(target);
    } catch (e) {
      console.warn('[LaunchScreen] Failed to fetch metadata schema:', e);
      metadataSchema = null;
    }
  }

  async function handleCreateSession() {
    if (!nsValid || nsSubmitting) return;
    nsSubmitting = true;
    error = null;
    try {
      const target = nsMetaTarget ? metadataTargets[nsMetaTarget] : '';
      const name = nsName.trim().toLowerCase().replace(/\s+/g, '-');
      await app.createSession(nsRoot, nsRig, name, target, nsMetadata);
      newSessionOpen = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to create session';
    } finally {
      nsSubmitting = false;
    }
  }

  async function handleResumeSession(session: SessionListing) {
    error = null;
    try {
      await app.resumeSession(session.directory.path);
      goto(resolve('/scout'));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to resume session';
    }
  }

  function openForkDialog(session: SessionListing) {
    forkTarget = session;
    forkSessionOpen = true;
  }

  async function handleForkSubmit() {
    if (!forkTarget || !fkValid || fkSubmitting) return;
    fkSubmitting = true;
    error = null;
    try {
      await app.forkSession(forkTarget.directory.path, fkRoot, fkName.trim(), fkDescription, fkClearStacks);
      forkSessionOpen = false;
      goto(resolve('/scout'));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to fork session';
    } finally {
      fkSubmitting = false;
    }
  }

  async function handleStarSession(session: SessionListing) {
    const current = session.config?.info.status;
    const next = current === 'starred' ? 'active' : 'starred';
    await app.updateSessionStatus(session.directory.path, next);
    await loadAllSessions();
  }

  async function handleArchiveSession(session: SessionListing) {
    const current = session.config?.info.status;
    const next = current === 'archived' ? 'active' : 'archived';
    await app.updateSessionStatus(session.directory.path, next);
    await loadAllSessions();
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

  function handleNsMetaTargetChange(key: string) {
    const target = metadataTargets[key];
    if (target) handleMetadataTargetChanged(target);
  }

  function setNsMetaValue(key: string, val: unknown) {
    nsMetadata = { ...nsMetadata, [key]: val };
  }
</script>

<!-- ── Session Card Snippet ── -->
{#snippet sessionCard(session: SessionListing)}
  {@const info = session.config?.info}
  {@const hasError = session.errors.length > 0}
  {@const isStarred = info?.status === 'starred'}
  {@const isArchived = info?.status === 'archived'}

  <div
    class={hasError
      ? 'rounded border border-danger/30 bg-danger/5 px-3 py-2.5'
      : 'rounded border border-border bg-card px-3 py-2.5'}
  >
    {#if hasError}
      <div class="flex w-full items-center gap-2">
        <span class="min-w-0 flex-1 truncate text-sm font-medium text-fg">
          {info?.name || session.directory.name}
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
            <span class="truncate">{info?.name || session.directory.name}</span>
          </Collapsible.Trigger>

          {#if isStarred}
            <Star width="12" height="12" class="shrink-0 fill-current text-fg-muted/60" />
          {/if}
          {#if isArchived}
            <Archive width="12" height="12" class="shrink-0 text-fg-muted/60" />
          {/if}

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
                <DropdownMenu.Item onclick={() => handleStarSession(session)}>
                  {#if isStarred}
                    <StarOff width="12" height="12" />
                  {:else}
                    <Star width="12" height="12" />
                  {/if}
                  {isStarred ? 'Unstar' : 'Star'}
                </DropdownMenu.Item>
                <DropdownMenu.Item onclick={() => handleArchiveSession(session)}>
                  <Archive width="12" height="12" />
                  {isArchived ? 'Unarchive' : 'Archive'}
                </DropdownMenu.Item>
                <DropdownMenu.Item onclick={() => openForkDialog(session)}>
                  <GitFork width="12" height="12" />
                  Fork
                </DropdownMenu.Item>
                <DropdownMenu.Separator />
                <DropdownMenu.Item onclick={() => copyPath(session.directory.path)}>
                  <Clipboard width="12" height="12" />
                  Copy path
                </DropdownMenu.Item>
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
              <span>{session.config?.rig.info.name ?? ''}</span>
              {#if info?.source}
                <span>Source</span>
                <span>
                  {info.source.type === 'fork' ? 'Forked from' : 'From'}
                  {info.source.name}
                </span>
              {/if}
              {#if info?.description}
                <span>Description</span>
                <span>{info.description}</span>
              {/if}
              {#if info?.status}
                <span>Status</span>
                <span class="capitalize">{info.status}</span>
              {/if}
              <span>Path</span>
              <div class="flex min-w-0 items-center gap-1">
                <span class="min-w-0 truncate">{session.directory.path}</span>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onclick={() => copyPath(session.directory.path)}
                  title="Copy path"
                >
                  <Clipboard width="10" height="10" />
                </Button>
              </div>
            </div>

            <div class="flex items-center gap-2 py-2">
              {#if info?.created_at}
                <span>Created {formatDate(info.created_at)}</span>
                <span>&middot;</span>
              {/if}
              <span>Modified {formatDate(session.directory.modified)}</span>
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
          <AppMenu {app} class="w-4" />
        </div>
        <p class="text-sm text-fg-muted">Light sheet microscopy</p>
      </div>

      {#if error}
        <div class="mb-4 rounded border border-danger/50 bg-danger/10 px-4 py-3 text-base text-danger">
          {error}
        </div>
      {/if}
    </div>

    {#if connectionState === 'failed'}
      <div class="flex flex-1 flex-col items-center justify-center gap-3">
        <p class="text-base text-danger">{app.client.connectionMessage}</p>
        <Button variant="outline" size="sm" onclick={() => app.retryConnection()}>Retry</Button>
      </div>
    {:else if !isIdle || isLaunching}
      <div class="flex flex-1 items-center justify-center gap-2">
        <div class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
        <p class="text-sm text-fg-muted">
          {isLaunching ? 'Starting session...' : app.client.connectionMessage}
        </p>
      </div>
    {:else}
      <!-- Toolbar -->
      <div class="flex items-center gap-2 px-4 py-3">
        <Button variant="ghost" size="sm" onclick={() => (newSessionOpen = true)}>
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
            {#each sessions as session (session.directory.path)}
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

<Dialog.Root bind:open={newSessionOpen}>
  <Dialog.Content size="xl">
    <Dialog.Header>
      <Dialog.Title>New Session</Dialog.Title>
    </Dialog.Header>

    <div class="grid grid-cols-2 gap-4">
      <Field label="Session Root">
        <Select options={rootOptions} bind:value={nsRoot} />
      </Field>

      <Field label="Rig Configuration">
        <Select options={rigs.map((r) => ({ value: r, label: r }))} bind:value={nsRig} />
      </Field>

      <Field label="Session Name" id="ns-name">
        <TextInput bind:value={nsName} id="ns-name" align="left" placeholder="Auto-generated if empty" />
      </Field>

      {#if Object.keys(metadataTargets).length > 0}
        <Field label="Metadata Target">
          <Select
            options={Object.keys(metadataTargets).map((k) => ({ value: k, label: sanitizeString(k) }))}
            bind:value={nsMetaTarget}
            onchange={handleNsMetaTargetChange}
          />
        </Field>
      {/if}

      {#if metadataSchema}
        <div class="col-span-full">
          <MetadataFields schema={metadataSchema} values={nsMetadata} onChange={setNsMetaValue}>
            {#snippet field(key, prop, input)}
              {@const fullSpan = key === 'notes' || prop.type === 'array' ? 'col-span-full' : ''}
              <div class={fullSpan}>
                <Field label={sanitizeString(key)}>
                  {@render input()}
                </Field>
              </div>
            {/snippet}
          </MetadataFields>
        </div>
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => (newSessionOpen = false)}>Cancel</Button>
      <Button variant="success" onclick={handleCreateSession} disabled={!nsValid || nsSubmitting}>
        {nsSubmitting ? 'Creating...' : 'Create Session'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<!-- ═══════════════════════════════════════════ -->
<!-- Fork Session Dialog                        -->
<!-- ═══════════════════════════════════════════ -->

<Dialog.Root bind:open={forkSessionOpen}>
  <Dialog.Content size="xl">
    {#if forkTarget}
      <Dialog.Header>
        <Dialog.Title>Fork Session</Dialog.Title>
        <Dialog.Description>
          Forking from: {fkSourceName}
        </Dialog.Description>
      </Dialog.Header>

      <div class="grid grid-cols-2 gap-4">
        <Field label="Session Root">
          <Select options={rootOptions} bind:value={fkRoot} />
        </Field>

        <Field label="Session Name">
          <TextInput bind:value={fkName} align="left" />
        </Field>

        <div class="col-span-2">
          <Field label="Description">
            <TextInput bind:value={fkDescription} align="left" />
          </Field>
        </div>

        <div class="col-span-2 flex items-center gap-2">
          <Checkbox bind:checked={fkClearStacks} />
          <span class="text-sm text-fg">Clear stacks</span>
          <span class="text-xs text-fg-muted">If unchecked, existing stacks are reset to planned</span>
        </div>
      </div>

      <Dialog.Footer>
        <Button variant="outline" onclick={() => (forkSessionOpen = false)}>Cancel</Button>
        <Button variant="success" onclick={handleForkSubmit} disabled={!fkValid || fkSubmitting}>
          {fkSubmitting ? 'Creating...' : 'Create Fork'}
        </Button>
      </Dialog.Footer>
    {/if}
  </Dialog.Content>
</Dialog.Root>
