<script lang="ts">
  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener, watch } from 'runed';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { toast } from 'svelte-sonner';

  import { goto, replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import type { ResolvedPathname } from '$app/types';
  import {
    activateDashboardWindow,
    DASHBOARD_WINDOW_NAME,
    getDashboardOpener,
    isStationWindowRequest,
    sendStationWindowRequest,
    stationWindowName,
    stationWindowRequest
  } from '$lib/app-windows';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import RoutingMonitor from '$lib/devices/RoutingMonitor.svelte';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import { Logout, Power } from '$lib/icons';
  import { Button, Dialog, Spinner } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { type PreviewMode, setVoxelStation, Station } from '$lib/model';
  import { PreviewSession, providePreviewContext } from '$lib/preview/session.svelte';
  import ProfileSelector from '$lib/ProfileSelector.svelte';
  import { instrumentPath, instrumentTargetPath, stationPath } from '$lib/routes';
  import RunButton from '$lib/RunButton.svelte';
  import StageGizmo from '$lib/stage/StageGizmo.svelte';
  import { cn, createPaneSize, displayName, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import ConnectionSplash from './ConnectionSplash.svelte';
  import InstrumentSelector from './InstrumentSelector.svelte';
  import WorkspaceViewer from './WorkspaceViewer.svelte';

  const { children } = $props();

  const app = new Station();
  setVoxelStation(app);
  const stationId = $derived(page.params.stationId ?? '');
  const previews = providePreviewContext();
  provideTaskSelection();

  $effect(() => {
    const instrument = app.instrument;
    if (!instrument) {
      previews.current = null;
      return;
    }
    const session = untrack(
      () =>
        new PreviewSession({
          client: app.client,
          instrumentId: instrument.id,
          stationId: instrument.stationId,
          sessionId: instrument.sessionId,
          websocketUrl: app.discovery.realtime.preview_websocket_url,
          protocolVersion: app.discovery.realtime.preview_protocol_version,
          detection: instrument.hal.detection,
          initialStatus: instrument.status,
          initialStateCursor: app.stateCursor,
          catalog: app.discovery.colormaps
        })
    );
    previews.current = session;
    return () => {
      if (previews.current === session) previews.current = null;
      session.dispose();
    };
  });

  $effect(() => {
    const instrument = app.instrument;
    const session = previews.current;
    if (!instrument || !session) return;
    const status = instrument.status;
    const cursor = app.stateCursor;
    untrack(() => session.applyInstrumentStatus(status, cursor));
  });

  onMount(() => {
    window.name = stationWindowName(stationId);
    void initializeShell();
  });
  onDestroy(() => {
    previews.current?.dispose();
    app.dispose();
  });
  useEventListener(window, 'beforeunload', () => {
    previews.current?.dispose();
    app.dispose();
  });
  useEventListener(window, 'message', (event) => {
    if (event.origin !== window.location.origin || !isStationWindowRequest(event.data)) return;
    if (event.data.stationId !== stationId) return;
    if (!app.ready) {
      deferredSelection = { instrumentId: event.data.instrumentId, open: event.data.open };
      return;
    }
    toastError(requestInstrumentSelection(event.data.instrumentId, event.data.open));
  });

  // --- Keyboard shortcuts ---

  createHotkey('Alt+P', () => {
    const inst = app.instrument;
    const preview = previews.current;
    if (!inst || !preview) return;
    if (inst.mode === 'preview') preview.stopPreview();
    else preview.startPreview();
  });
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (app.instrument) showCloseDialog();
  });

  // --- Shell nav ---

  type Route = { id: string; label: string };
  type Segment = {
    key: string;
    label: string;
    highlighted: boolean;
    select: () => void;
  };

  const inspectRoute: Route = { id: '/', label: 'Inspect' };
  const workflowRoutes: Route[] = [
    { id: '/sync', label: 'Sync' },
    { id: '/configure', label: 'Configure' },
    { id: '/plan', label: 'Plan' },
    { id: '/run', label: 'Run' }
  ];
  const selectedInstrumentId = $derived(page.params.instrumentId ?? '');
  const instrumentId = $derived(app.activeName ?? selectedInstrumentId);
  const stationName = $derived(app.discovery.station.name || displayName(stationId));
  const windowTitle = $derived(`Voxel — ${stationName}`);
  const instrumentInspection = $derived(instrumentId ? app.discovery.instruments[instrumentId] : undefined);
  const instrumentHasIssue = $derived(
    instrumentInspection
      ? instrumentInspection.config.status !== 'loaded' || instrumentInspection.violations.length > 0
      : false
  );
  const instrumentTransition = $derived(
    app.openingName !== null || app.stationStatus === 'opening' || app.stationStatus === 'closing'
  );
  const instrumentTransitionLabel = $derived(
    app.stationStatus === 'closing' ? 'Closing instrument' : 'Opening instrument'
  );
  const canOpenInstrument = $derived(
    app.stationStatus === 'idle' && !!instrumentInspection && !instrumentHasIssue && app.openingName === null
  );
  const openInstrumentTitle = $derived(
    instrumentHasIssue
      ? 'Resolve the instrument configuration before opening it'
      : app.stationStatus === 'faulted'
        ? 'The station must be recovered before opening an instrument'
        : app.stationStatus === 'closed'
          ? 'The station is closed'
          : 'Open instrument'
  );
  /** Configuration issues remain visible while the instrument is offline; active state is conveyed by the controls. */
  const instrumentStatusDot = $derived<{ tone: string; label: string } | null>(
    instrumentHasIssue ? { tone: 'bg-danger', label: 'Configuration issue' } : null
  );
  const operateRoot = $derived(instrumentPath(stationId, instrumentId));

  function operateRelativePath(pathname: string): string | null {
    if (pathname === operateRoot) return '/';
    return pathname.startsWith(`${operateRoot}/`) ? pathname.slice(operateRoot.length) : null;
  }

  const currentPath = $derived(operateRelativePath(page.url.pathname) ?? '');
  const inspectActive = $derived(page.route.id?.includes('/(inspect)') ?? false);
  const activeWorkflow = $derived(workflowRoutes.find((route) => currentPath.startsWith(route.id))?.id ?? null);
  const inspectPaths = new SvelteMap<string, ResolvedPathname>();

  function inspectPathKey(station: string, instrument: string): string {
    return `${station}\u0000${instrument}`;
  }

  watch(
    () => [inspectActive, stationId, page.params.instrumentId, page.url.pathname] as const,
    ([active, station, routeInstrumentId, pathname]) => {
      if (active && routeInstrumentId) {
        inspectPaths.set(inspectPathKey(station, routeInstrumentId), pathname as ResolvedPathname);
      }
    }
  );

  async function initializeShell(): Promise<void> {
    try {
      await app.initialize(stationId);
      const shouldOpen = page.url.searchParams.get('open') === '1';
      if (shouldOpen) {
        replaceState(instrumentPath(stationId, selectedInstrumentId), page.state);
      }
      if (deferredSelection) {
        const request = deferredSelection;
        deferredSelection = null;
        await requestInstrumentSelection(request.instrumentId, request.open);
        return;
      }
      if (!selectedInstrumentId) return;
      if (app.activeName && app.activeName !== selectedInstrumentId) {
        pendingSwitch = { instrumentId: selectedInstrumentId, open: shouldOpen };
        closeDialogOpen = true;
      } else if (shouldOpen && !app.activeName) {
        await app.launch(selectedInstrumentId);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }

  watch(
    () => [app.activeTarget, activeWorkflow] as const,
    ([activeTarget, currentWorkflow]) => {
      if (activeTarget === null && currentWorkflow !== null) {
        goto(operateRoot, { replaceState: true });
      }
    }
  );

  function selectView(id: string) {
    const selected = id === inspectRoute.id ? inspectActive : activeWorkflow === id;
    if (selected || !instrumentId) return;
    const target =
      id === inspectRoute.id
        ? (inspectPaths.get(inspectPathKey(stationId, instrumentId)) ?? operateRoot)
        : instrumentTargetPath(stationId, instrumentId, id);
    goto(target, { keepFocus: true, noScroll: true });
  }

  function instrumentInspectPath(name: string): ResolvedPathname {
    return inspectPaths.get(inspectPathKey(stationId, name)) ?? instrumentPath(stationId, name);
  }

  async function requestInstrumentSelection(name: string, open: boolean): Promise<void> {
    if (instrumentTransition) return;
    if (app.activeName && app.activeName !== name) {
      pendingSwitch = { instrumentId: name, open };
      closeDialogOpen = true;
      return;
    }

    const target = open ? instrumentPath(stationId, name) : instrumentInspectPath(name);
    await goto(target, { keepFocus: true, noScroll: true });
    if (open && !app.activeName) await app.launch(name);
  }

  function selectInstrument(targetStationId: string, name: string): void {
    if (targetStationId === stationId) {
      toastError(requestInstrumentSelection(name, false));
      return;
    }

    const target = instrumentPath(targetStationId, name);
    const controlWindow = window.open('', stationWindowName(targetStationId));
    if (!controlWindow) {
      toast.error('The station window was blocked by the browser.');
      return;
    }
    if (controlWindow.location.href === 'about:blank') controlWindow.location.href = target;
    else sendStationWindowRequest(controlWindow, stationWindowRequest(targetStationId, name, false));
    controlWindow.focus();
  }

  function resolveDashboardWindow(): Window | null {
    return getDashboardOpener() ?? window.open(stationPath(stationId), DASHBOARD_WINDOW_NAME);
  }

  function showDashboard(): void {
    if (activateDashboardWindow(stationPath(stationId))) return;
    void goto(stationPath(stationId), { keepFocus: true, noScroll: true });
  }

  function openInstrument(): void {
    if (!instrumentId || !canOpenInstrument) return;
    toastError(app.launch(instrumentId));
  }

  function showCloseDialog(): void {
    pendingSwitch = null;
    closeDialogOpen = true;
  }

  function cancelClose(): void {
    closeDialogOpen = false;
    pendingSwitch = null;
  }

  async function closeInstrument(exit: boolean): Promise<void> {
    const name = app.activeName;
    if (!name) return;
    const instrumentOverview = instrumentPath(stationId, name);
    if (!exit) {
      await app.close();
      await goto(instrumentOverview, { keepFocus: true, noScroll: true });
      return;
    }

    const dashboardPath = stationPath(stationId);
    // Resolve the named dashboard while the confirmation click still carries user activation.
    const dashboardWindow = resolveDashboardWindow();
    await app.close();
    if (!dashboardWindow) {
      await goto(dashboardPath, { keepFocus: true, noScroll: true });
      return;
    }
    dashboardWindow.focus();
    window.close();
    if (window.closed) return;
    await goto(dashboardPath, { keepFocus: true, noScroll: true });
  }

  async function confirmClose(): Promise<void> {
    if (closingInstrument) return;
    closingInstrument = true;
    try {
      if (pendingSwitch) {
        const target = pendingSwitch;
        await app.close();
        await goto(instrumentInspectPath(target.instrumentId), { keepFocus: true, noScroll: true });
        closeDialogOpen = false;
        pendingSwitch = null;
        if (target.open) await app.launch(target.instrumentId);
      } else {
        await closeInstrument(false);
        closeDialogOpen = false;
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      closingInstrument = false;
    }
  }

  async function confirmCloseAndExit(): Promise<void> {
    if (closingInstrument) return;
    closingInstrument = true;
    try {
      await closeInstrument(true);
      closeDialogOpen = false;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      closingInstrument = false;
    }
  }

  const inspectSegment = $derived<Segment>({
    key: inspectRoute.id,
    label: inspectRoute.label,
    highlighted: inspectActive,
    select: () => selectView(inspectRoute.id)
  });
  const workflowSegments = $derived<Segment[]>(
    workflowRoutes.map((route) => ({
      key: route.id,
      label: route.label,
      highlighted: activeWorkflow === route.id,
      select: () => selectView(route.id)
    }))
  );
  /** True when the current view is a workflow step — used to brighten the nav border. */
  const workflowActive = $derived(activeWorkflow !== null);

  const previewModes: { mode: PreviewMode; label: string }[] = [
    { mode: 'live', label: 'Live' },
    { mode: 'stage', label: 'Stage' }
  ];

  // Pane sizes
  let shellRef = $state<HTMLElement | null>(null);
  let instrumentControl = $state<HTMLElement | null>(null);
  const contentPane = createPaneSize(() => shellRef, {
    min: 45,
    default: 45,
    fallback: { min: 30, default: 30 }
  });
  const viewerPane = createPaneSize(() => shellRef, {
    min: 60,
    fallback: { min: 40 }
  });

  const monitorsPane = createPaneSize(() => shellRef, {
    min: 28,
    default: 28,
    max: 28,
    fallback: { min: 15, max: 15 }
  });

  // Vertical split inside the monitors pane: telemetry (top) over the stage gizmo (bottom).
  let monitorsSplitEl = $state<HTMLElement | null>(null);
  const gizmoPane = createPaneSize(() => monitorsSplitEl, {
    default: 22,
    min: 18,
    max: 28,
    fallback: { min: 28, max: 40, default: 32 }
  });

  // --- Dialog state ---

  type PendingSwitch = { instrumentId: string; open: boolean };

  let closeDialogOpen = $state(false);
  let pendingSwitch = $state<PendingSwitch | null>(null);
  let deferredSelection = $state<PendingSwitch | null>(null);
  let closingInstrument = $state(false);
</script>

<svelte:head>
  <title>{windowTitle}</title>
</svelte:head>

{#if !app.client.isConnected || !app.ready}
  <ConnectionSplash {app} />
{:else}
  {#snippet routeLink(segment: Segment)}
    <button
      type="button"
      title={segment.label}
      onclick={segment.select}
      class={cn(
        'inline-flex h-full cursor-pointer items-center justify-center px-2 text-lg font-normal whitespace-nowrap transition-colors',
        segment.highlighted ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover/80 hover:text-fg'
      )}
    >
      {segment.label}
    </button>
  {/snippet}
  {#snippet viewModeSelector()}
    <div class="ml-auto flex h-ui-md shrink-0 items-center rounded-md border border-input bg-canvas/50 p-0.5">
      {#each previewModes as { mode, label } (mode)}
        <button
          type="button"
          title={label}
          onclick={() => app.viewMode.set(mode)}
          class={cn(
            'inline-flex h-full min-w-16 cursor-pointer items-center justify-center rounded-sm px-3 text-lg whitespace-nowrap transition-colors',
            app.viewMode.get() === mode ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
          )}
        >
          {label}
        </button>
      {/each}
    </div>
  {/snippet}
  {#snippet dashboardButton()}
    <button
      type="button"
      onclick={showDashboard}
      class="ml-auto flex h-ui-md shrink-0 items-center gap-2 rounded-md border border-border px-2 text-fg transition-colors hover:bg-element-hover"
      title="Open dashboard"
      aria-label="Open dashboard"
    >
      <span class="text-2xl font-normal tracking-wide uppercase">Voxel</span>
      <VoxelLogo class="size-6 shrink-0" />
    </button>
  {/snippet}
  <main bind:this={shellRef} class="h-screen w-screen text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell:frame" class="h-full w-full bg-surface text-fg">
      <Pane {...contentPane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
        <header class="pane-header">
          <!-- An instrument is in scope (open, or named in the URL) — offer the Inspect button. -->
          {#if instrumentId}
            <div
              bind:this={instrumentControl}
              class={cn(
                '-ml-1 flex h-ui-md shrink items-stretch divide-x divide-border overflow-hidden rounded-md border transition-colors',
                inspectSegment.highlighted ? 'border-border bg-element-selected' : 'border-border-faint'
              )}
            >
              <InstrumentSelector
                {stationId}
                instrumentId={selectedInstrumentId || instrumentId}
                anchor={instrumentControl}
                disabled={instrumentTransition}
                onselect={selectInstrument}
              />
              <button
                type="button"
                onclick={inspectSegment.select}
                class={cn(
                  'flex max-w-64 min-w-45 shrink items-center gap-2 px-2 transition-colors',
                  inspectSegment.highlighted ? 'text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                )}
                title={`Inspect ${displayName(instrumentId)}`}
                aria-label={`Inspect ${displayName(instrumentId)}`}
              >
                <span class="truncate text-lg">{displayName(instrumentId)}</span>
                {#if instrumentStatusDot}
                  <span
                    class={cn('size-1.5 shrink-0 rounded-full', instrumentStatusDot.tone)}
                    title={instrumentStatusDot.label}
                  >
                    <span class="sr-only">{instrumentStatusDot.label}</span>
                  </span>
                {/if}
              </button>
              {#if instrumentTransition}
                <span
                  class="flex w-7 shrink-0 items-center justify-center text-fg-muted"
                  title={instrumentTransitionLabel}
                >
                  <Spinner class="size-3.5" aria-label={instrumentTransitionLabel} />
                </span>
              {:else if app.instrument}
                <button
                  type="button"
                  title="Close instrument"
                  aria-label="Close instrument"
                  onclick={showCloseDialog}
                  class="flex w-7 shrink-0 cursor-pointer items-center justify-center text-fg-muted transition-colors hover:bg-element-hover/80 hover:text-danger"
                >
                  <Logout width="14" height="14" />
                </button>
              {:else}
                <button
                  type="button"
                  title={openInstrumentTitle}
                  aria-label={openInstrumentTitle}
                  disabled={!canOpenInstrument}
                  onclick={openInstrument}
                  class="flex w-7 shrink-0 cursor-pointer items-center justify-center text-fg-muted transition-colors hover:bg-element-hover/80 hover:text-success disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-fg-muted"
                >
                  <Power width="14" height="14" />
                </button>
              {/if}
            </div>
          {/if}
          <!-- Stricter: the workflow steps need a loaded instrument, not just a name. -->
          {#if app.instrument}
            <div
              class={cn(
                'ml-auto flex h-ui-md items-stretch overflow-hidden rounded-md border',
                workflowActive ? 'border-border' : 'border-border-faint'
              )}
            >
              <nav aria-label="Instrument workflow" class="grid h-full grid-flow-col divide-x divide-border">
                {#each workflowSegments as segment (segment.key)}
                  {@render routeLink(segment)}
                {/each}
              </nav>
            </div>
          {/if}
        </header>
        <div class="flex min-h-0 min-w-0 flex-col overflow-hidden">
          {@render children()}
        </div>
      </Pane>
      <PaneDivider direction="vertical" />
      <Pane {...viewerPane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)] ">
        <header class="pane-header">
          {#if app.instrument}
            <ProfileSelector instrument={app.instrument} size="md" class="w-64 min-w-36 shrink" />
            {@render viewModeSelector()}
          {:else}
            {@render dashboardButton()}
          {/if}
        </header>
        <div class="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <WorkspaceViewer />
        </div>
      </Pane>
      {#if app.instrument}
        {@const instrument = app.instrument}
        <PaneDivider direction="vertical" />
        <Pane {...monitorsPane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
          <header class="pane-header justify-end">
            <RunButton {app} class="min-w-0 flex-1 justify-center" />
            {@render dashboardButton()}
          </header>
          <PaneGroup direction="vertical" bind:ref={monitorsSplitEl} autoSaveId="shell:monitors" class="min-h-0 flex-1">
            <Pane class="min-h-0">
              <div class="flex h-full flex-col divide-y divide-border overflow-y-auto">
                {#if instrument.cameras.size > 0}
                  <CamerasMonitor {instrument} />
                {/if}
                {#if instrument.lasers.size > 0}
                  <LasersMonitor {instrument} />
                {/if}
                {#if instrument.filterWheels.length > 0}
                  <FilterWheelsMonitor {instrument} />
                {/if}
                {#if Object.keys(instrument.hal.optical_routing).length > 0}
                  <RoutingMonitor {instrument} />
                {/if}
              </div>
            </Pane>
            <PaneDivider direction="horizontal" />
            <Pane defaultSize={32} {...gizmoPane} class="min-h-0">
              <StageGizmo stage={instrument.stage} class="border-t border-border p-3" />
            </Pane>
          </PaneGroup>
        </Pane>
      {/if}
    </PaneGroup>
  </main>
  <Dialog.Root bind:open={closeDialogOpen}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>{pendingSwitch ? 'Switch instrument?' : 'Close instrument'}</Dialog.Title>
      </Dialog.Header>
      <p class="text-lg text-fg-muted">
        {#if pendingSwitch}
          Close <span class="font-medium text-fg">{displayName(app.activeName ?? 'the active instrument')}</span> and
          {pendingSwitch.open ? 'open' : 'inspect'}
          <span class="font-medium text-fg">{displayName(pendingSwitch.instrumentId)}</span>? The current instrument's
          hardware will be disconnected.
        {:else}
          Are you sure you want to close
          <span class="font-medium text-fg">{displayName(app.activeName ?? 'the active instrument')}</span>? Its
          hardware will be disconnected.
        {/if}
      </p>
      <Dialog.Footer>
        <Button variant="ghost" disabled={closingInstrument} onclick={cancelClose}>Cancel</Button>
        <Button variant="danger" disabled={closingInstrument} onclick={confirmClose}>
          {closingInstrument ? 'Closing…' : pendingSwitch ? 'Close and switch' : 'Close'}
        </Button>
        {#if !pendingSwitch}
          <Button variant="danger" disabled={closingInstrument} onclick={confirmCloseAndExit}>Close & Exit</Button>
        {/if}
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}

<style>
  /* Shared header bar for the three shell columns. */
  .pane-header {
    display: flex;
    height: calc(var(--spacing) * 12);
    flex-shrink: 0;
    align-items: center;
    gap: calc(var(--spacing) * 3);
    padding-inline: calc(var(--spacing) * 3);
    border-bottom: 1px solid var(--border);
    background-color: var(--elevated);
  }
</style>
