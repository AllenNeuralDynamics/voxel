<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { AlertCircleOutline } from '$lib/icons';
  import { buildDeviceTopology, groupDevicesForNavigation } from '$lib/instruments/device-topology';
  import { resolveInstrumentView, violationLocation } from '$lib/instruments/instrument-view';
  import { Button, Dialog, Sidebar } from '$lib/kit';
  import { ApiError, getVoxelStation, type Violation } from '$lib/model';
  import { configurePath, instrumentDevicePath } from '$lib/routes';
  import { displayName } from '$lib/utils';

  import LibraryBreadcrumb, { type LibraryBreadcrumbItem } from '../../../LibraryBreadcrumb.svelte';
  import { setInstrumentPageContext } from '../../instrument-page-context';
  import { instrumentSectionPath, instrumentSections, parseInstrumentSectionPath } from '../../sections';

  const { children } = $props();
  const app = getVoxelStation();

  const stationId = $derived(page.params.stationId);
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const instrumentState = $derived(activeInstrument?.state ?? selected?.state ?? null);
  const topology = $derived(hal && instrumentState ? buildDeviceTopology(hal, instrumentState.imaging) : null);
  const acquisitions = $derived(id ? app.acquisitions.filter((manifest) => manifest.instrument === id) : []);
  const location = $derived(parseInstrumentSectionPath(stationId, page.url.pathname));
  const section = $derived(instrumentSections.find(({ id: sectionId }) => sectionId === location?.section));
  const deviceId = $derived(page.params.deviceId);
  const acquisitionId = $derived(page.params.acquisitionId);
  const acquisition = $derived(
    acquisitionId ? (acquisitions.find((manifest) => manifest.id === acquisitionId) ?? null) : null
  );
  const acquisitionDateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  });
  const sections = $derived(
    selected
      ? instrumentSections.filter(({ id: sectionId }) => sectionId !== 'overview' && sectionId !== 'devices')
      : instrumentSections.filter(({ id: sectionId }) => sectionId === 'acquisitions')
  );
  const deviceGroups = $derived(topology ? groupDevicesForNavigation(topology) : []);
  const instrumentLabel = $derived(
    selected ? displayName(selected.name) : id && acquisitions.length ? displayName(id) : 'Instrument not found'
  );
  const breadcrumbItems = $derived.by<LibraryBreadcrumbItem[]>(() => {
    if (!location || !id) return [];
    if (location.section === 'overview') return [{ label: section?.label ?? 'Overview' }];

    const items: LibraryBreadcrumbItem[] = [];

    if (section) {
      items.push({
        label: section.label,
        href:
          deviceId && location.section === 'devices'
            ? `${instrumentSectionPath(stationId, id, 'overview')}#devices`
            : acquisitionId && location.section === 'acquisitions'
              ? instrumentSectionPath(stationId, id, 'acquisitions')
              : undefined
      });
    }
    if (deviceId) items.push({ label: displayName(deviceId), title: displayName(deviceId) });
    if (acquisitionId) {
      items.push({
        label: acquisition ? acquisitionDateFormat.format(new Date(acquisition.created_at)) : 'Acquisition',
        title: acquisitionId
      });
    }
    return items;
  });

  let launchFailure = $state<Violation[] | null>(null);
  let archiveStateDialogOpen = $state(false);

  watch(
    () => id,
    () => {
      launchFailure = null;
    }
  );

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

    if (launchFailure) {
      return {
        title: `Unable to open ${id ? displayName(id) : 'instrument'}`,
        description: 'Hardware startup did not complete. Review the reported issues and retry when they are resolved.',
        source: 'startup' as const,
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
      await goto(configurePath(stationId, id));
    } catch (error) {
      launchFailure = parseViolations(error);
    }
  }

  function devicePath(targetId: string) {
    return instrumentDevicePath(stationId, id ?? '', targetId);
  }

  function deviceIssue(targetId: string): { label: string; class: string } | null {
    const device = activeInstrument?.devices.get(targetId);
    if (!device) return null;
    if (device.error) return { label: device.error, class: 'bg-danger' };
    if (!device.connected) return { label: 'Disconnected', class: 'bg-warning' };
    return null;
  }

  setInstrumentPageContext({
    get opening() {
      return app.busy || app.openingName !== null || app.stationStatus === 'opening';
    },
    open: openInstrument
  });

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

<Sidebar.Provider class="h-full min-h-0 overflow-hidden">
  <Sidebar.Root
    collapsible="none"
    class="w-54 shrink-0 overflow-hidden border-r border-border"
    role="navigation"
    aria-label={`${instrumentLabel} navigation`}
  >
    <Sidebar.Content>
      <Sidebar.Group class="py-2">
        <Sidebar.Menu>
          {#if id}
            <Sidebar.MenuItem>
              <Sidebar.MenuButton isActive={location?.section === 'overview'}>
                {#snippet child({ props })}
                  <a
                    {...props}
                    href={instrumentSectionPath(stationId, id, 'overview')}
                    aria-current={location?.section === 'overview' ? 'page' : undefined}
                  >
                    <span>Overview</span>
                  </a>
                {/snippet}
              </Sidebar.MenuButton>
            </Sidebar.MenuItem>

            {#each sections as instrumentSection (instrumentSection.id)}
              {@const current = location?.section === instrumentSection.id}
              <Sidebar.MenuItem>
                <Sidebar.MenuButton isActive={current}>
                  {#snippet child({ props })}
                    <a
                      {...props}
                      href={instrumentSectionPath(stationId, id, instrumentSection.id)}
                      aria-current={current ? 'page' : undefined}
                    >
                      <span>{instrumentSection.label}</span>
                    </a>
                  {/snippet}
                </Sidebar.MenuButton>
              </Sidebar.MenuItem>
            {/each}
          {/if}
        </Sidebar.Menu>
      </Sidebar.Group>

      {#each deviceGroups as deviceGroup (deviceGroup.id)}
        <Sidebar.Group class="py-2">
          <Sidebar.GroupLabel>{deviceGroup.label}</Sidebar.GroupLabel>
          <Sidebar.Menu>
            {#each deviceGroup.deviceIds as targetId (targetId)}
              {@const current = location?.section === 'devices' && deviceId === targetId}
              {@const issue = deviceIssue(targetId)}
              <Sidebar.MenuItem>
                <Sidebar.MenuButton isActive={current} title={displayName(targetId)}>
                  {#snippet child({ props })}
                    <a {...props} href={devicePath(targetId)} aria-current={current ? 'page' : undefined}>
                      <span class="truncate">{displayName(targetId)}</span>
                      {#if issue}
                        <span class={`ml-auto size-1.5 shrink-0 rounded-full ${issue.class}`} title={issue.label}
                        ></span>
                        <span class="sr-only">{issue.label}</span>
                      {/if}
                    </a>
                  {/snippet}
                </Sidebar.MenuButton>
              </Sidebar.MenuItem>
            {/each}
          </Sidebar.Menu>
        </Sidebar.Group>
      {/each}
    </Sidebar.Content>
  </Sidebar.Root>

  <main class="min-h-0 min-w-0 flex-1 overflow-hidden">
    <div class="flex h-full min-h-0 flex-col gap-1">
      {#if breadcrumbItems.length > 0}
        <div class="shrink-0 px-4 pt-3">
          <LibraryBreadcrumb items={breadcrumbItems} />
        </div>
      {/if}

      {#if selected || acquisitions.length > 0}
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
                        <span class="font-mono text-xs wrap-anywhere text-fg-muted">{violationLocation(violation)}</span
                        >
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

        <div class="min-h-0 flex-1 overflow-y-auto">
          {@render children()}
        </div>
      {:else}
        <div class="flex h-full items-center justify-center p-8">
          <p class="text-lg text-fg-muted">This instrument is not in the catalog.</p>
        </div>
      {/if}
    </div>
  </main>
</Sidebar.Provider>

<Dialog.Root bind:open={archiveStateDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Archive State</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />
    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        Archive <span class="font-medium text-fg">{id ? displayName(id) : ''}</span>'s current state so it reopens with
        its configured defaults. The archived state is retained as
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
