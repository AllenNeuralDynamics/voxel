<script lang="ts">
  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener, watch } from 'runed';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import type { ResolvedPathname } from '$app/types';
  import { activateDashboardWindow, DASHBOARD_WINDOW_NAME, getDashboardOpener } from '$lib/app-windows';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import RoutingMonitor from '$lib/devices/RoutingMonitor.svelte';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import { Logout, Microscope, Power } from '$lib/icons';
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

  onMount(() => toastError(app.initialize(stationId)));
  onDestroy(() => {
    previews.current?.dispose();
    app.dispose();
  });
  useEventListener(window, 'beforeunload', () => {
    previews.current?.dispose();
    app.dispose();
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
    if (app.instrument) closeDialogOpen = true;
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
  const instrumentId = $derived(app.activeName ?? page.params.instrumentId ?? '');
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
  /** Dot on the instrument button: green when it is the open one, red when its config is broken. */
  const instrumentStatusDot = $derived<{ tone: string; label: string } | null>(
    app.activeName === instrumentId
      ? { tone: 'bg-success', label: 'Active instrument' }
      : instrumentHasIssue
        ? { tone: 'bg-danger', label: 'Configuration issue' }
        : null
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

  let closeDialogOpen = $state(false);
</script>

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
              class={cn(
                '-ml-1 flex h-ui-md shrink items-stretch divide-x divide-border overflow-hidden rounded-md border transition-colors',
                inspectSegment.highlighted ? 'border-border bg-element-selected' : 'border-border-faint'
              )}
            >
              <button
                type="button"
                onclick={inspectSegment.select}
                class={cn(
                  'flex max-w-64 min-w-52 shrink items-center gap-2 px-2 transition-colors',
                  inspectSegment.highlighted ? 'text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                )}
                title={`Inspect ${displayName(instrumentId)}`}
                aria-label={`Inspect ${displayName(instrumentId)}`}
              >
                <Microscope width="14" height="14" class="shrink-0" />
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
                  onclick={() => (closeDialogOpen = true)}
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
        <Dialog.Title>Close instrument</Dialog.Title>
      </Dialog.Header>
      <p class="text-lg text-fg-muted">
        Are you sure you want to close
        <span class="font-medium text-fg">{displayName(app.activeName ?? 'the active instrument')}</span>? Its hardware
        will be disconnected.
      </p>
      <Dialog.Footer>
        <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
        <Button
          variant="danger"
          onclick={() => {
            closeDialogOpen = false;
            toastError(closeInstrument(false));
          }}
        >
          Close
        </Button>
        <Button
          variant="danger"
          onclick={() => {
            closeDialogOpen = false;
            toastError(closeInstrument(true));
          }}
        >
          Close & Exit
        </Button>
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
