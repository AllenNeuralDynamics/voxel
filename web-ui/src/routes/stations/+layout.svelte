<script lang="ts">
  import { createHotkey, createHotkeySequence, detectPlatform } from '@tanstack/svelte-hotkeys';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener, watch } from 'runed';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { toast } from 'svelte-sonner';

  import { goto, replaceState } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { activateDashboardWindow, isStationWindowRequest, stationWindowName } from '$lib/app-windows';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import { Power, Redo, Undo } from '$lib/icons';
  import { Button, Dialog, Sidebar, Spinner } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { setVoxelStation, Station } from '$lib/model';
  import { PreviewSession, providePreviewContext } from '$lib/preview/session.svelte';
  import { createPaneSize, displayName, toastError } from '$lib/utils';

  import CenterPane from './CenterPane.svelte';
  import ConnectionSplash from './ConnectionSplash.svelte';
  import InstrumentNavigation from './InstrumentNavigation.svelte';
  import MonitorsPane from './MonitorsPane.svelte';
  import StationMenu from './StationMenu.svelte';

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

  for (const [hotkey, action] of [
    ['Mod+Z', 'undo'],
    ['Mod+Shift+Z', 'redo'],
    ['Control+Y', 'redo']
  ] as const) {
    createHotkey(
      hotkey,
      (event) => {
        if (event.defaultPrevented || event.isComposing || event.repeat) return;
        if (hotkey === 'Control+Y' && detectPlatform() === 'mac') return;
        const instrument = app.instrument;
        if (!instrument || !canReplayHistory || instrument.history[`${action}_label`] === null) return;
        event.preventDefault();
        void replayHistory(action);
      },
      // Preserve native editing and only consume shortcuts that pass our guards.
      { ignoreInputs: true, preventDefault: false, stopPropagation: false }
    );
  }

  // --- Shell nav ---

  const workflowRoutes = ['/plan', '/grid'] as const;
  let lastSelection = $state<{ stationId: string; instrumentId: string } | null>(null);
  const selectedInstrumentId = $derived(
    page.params.instrumentId ?? (lastSelection?.stationId === stationId ? lastSelection.instrumentId : '')
  );
  const instrumentId = $derived(app.activeName ?? selectedInstrumentId);
  const routeParams = $derived({ stationId, instrumentId });
  const stationName = $derived(app.discovery.station.name || displayName(stationId));
  const windowTitle = $derived(`Voxel — ${stationName}`);
  const instrumentTransition = $derived(
    app.openingName !== null || app.stationStatus === 'opening' || app.stationStatus === 'closing'
  );
  const instrumentInspection = $derived(instrumentId ? app.discovery.instruments[instrumentId] : undefined);
  const instrumentHasIssue = $derived(
    instrumentInspection
      ? instrumentInspection.config.status !== 'loaded' || instrumentInspection.violations.length > 0
      : false
  );
  const canOpenInstrument = $derived(
    app.stationStatus === 'idle' && !!instrumentInspection && !instrumentHasIssue && app.openingName === null
  );
  const canReplayHistory = $derived(
    app.client.isConnected &&
      app.stationStatus === 'active' &&
      app.instrument?.mode !== 'capture' &&
      !app.instrument?.edits.busy
  );

  async function replayHistory(action: 'undo' | 'redo'): Promise<void> {
    const instrument = app.instrument;
    if (!instrument || !canReplayHistory || instrument.history[`${action}_label`] === null) return;
    try {
      await instrument[action]();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }

  const openInstrumentTitle = $derived(
    instrumentHasIssue
      ? 'Resolve the instrument configuration before opening it'
      : app.stationStatus === 'faulted'
        ? 'The station must be recovered before opening an instrument'
        : app.stationStatus === 'closed'
          ? 'The station is closed'
          : 'Open instrument'
  );
  const operateRoot = $derived(resolve('/stations/[stationId]/instruments/[instrumentId]', routeParams));

  function operateRelativePath(pathname: string): string | null {
    if (pathname === operateRoot) return '/';
    return pathname.startsWith(`${operateRoot}/`) ? pathname.slice(operateRoot.length) : null;
  }

  const currentPath = $derived(operateRelativePath(page.url.pathname) ?? '');
  const activeWorkflow = $derived(workflowRoutes.find((route) => currentPath.startsWith(route)) ?? null);

  function lastInstrumentKey(station: string): string {
    return `voxel:last-instrument:${station}`;
  }

  function rememberInstrument(station: string, instrument: string): void {
    try {
      window.localStorage.setItem(lastInstrumentKey(station), instrument);
    } catch {
      // Selection still works when browser storage is unavailable.
    }
  }

  watch(
    () => [stationId, page.params.instrumentId] as const,
    ([station, routeInstrumentId]) => {
      if (routeInstrumentId) {
        lastSelection = { stationId: station, instrumentId: routeInstrumentId };
        rememberInstrument(station, routeInstrumentId);
      }
    }
  );

  async function initializeShell(): Promise<void> {
    try {
      await app.initialize(stationId);
      const shouldOpen = page.url.searchParams.get('open') === '1';
      if (shouldOpen) {
        replaceState(
          resolve('/stations/[stationId]/instruments/[instrumentId]', {
            stationId,
            instrumentId: selectedInstrumentId
          }),
          page.state
        );
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

  async function requestInstrumentSelection(name: string, open: boolean): Promise<void> {
    if (instrumentTransition) return;
    if (app.activeName && app.activeName !== name) {
      pendingSwitch = { instrumentId: name, open };
      closeDialogOpen = true;
      return;
    }

    const target = resolve('/stations/[stationId]/instruments/[instrumentId]', { stationId, instrumentId: name });
    await goto(target, { keepFocus: true, noScroll: true });
    if (open && !app.activeName) await app.launch(name);
  }

  function selectInstrument(targetStationId: string, name: string): void {
    if (instrumentTransition) return;
    if (targetStationId === stationId) {
      if (app.activeName && app.activeName !== name) {
        toast.error('Close the current instrument before selecting another one.');
        return;
      }
      toastError(requestInstrumentSelection(name, false));
      return;
    }

    rememberInstrument(targetStationId, name);
    const target = resolve('/stations/[stationId]/instruments/[instrumentId]', {
      stationId: targetStationId,
      instrumentId: name
    });
    const controlWindow = window.open(target, stationWindowName(targetStationId));
    if (!controlWindow) {
      toast.error('The station window was blocked by the browser.');
      return;
    }
    controlWindow.focus();
  }

  function showDashboard(): void {
    if (activateDashboardWindow(resolve('/(dashboard)/stations/[stationId]', { stationId }))) return;
    void goto(resolve('/(dashboard)/stations/[stationId]', { stationId }), { keepFocus: true, noScroll: true });
  }

  function showSettings(): void {
    void goto(resolve('/stations/[stationId]/settings', { stationId }), { keepFocus: true, noScroll: true });
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

  async function closeInstrument(): Promise<void> {
    const name = app.activeName;
    if (!name) return;
    const instrumentOverview = resolve('/stations/[stationId]/instruments/[instrumentId]', {
      stationId,
      instrumentId: name
    });
    await app.close();
    await goto(instrumentOverview, { keepFocus: true, noScroll: true });
  }

  async function confirmClose(): Promise<void> {
    if (closingInstrument) return;
    closingInstrument = true;
    try {
      if (pendingSwitch) {
        const target = pendingSwitch;
        await app.close();
        await goto(
          resolve('/stations/[stationId]/instruments/[instrumentId]', { stationId, instrumentId: target.instrumentId }),
          { keepFocus: true, noScroll: true }
        );
        closeDialogOpen = false;
        pendingSwitch = null;
        if (target.open) await app.launch(target.instrumentId);
      } else {
        await closeInstrument();
        closeDialogOpen = false;
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      closingInstrument = false;
    }
  }

  // Pane sizes
  let frameRef = $state<HTMLElement | null>(null);
  const contentPane = createPaneSize(() => frameRef, {
    min: 32,
    max: 48,
    default: 32,
    fallback: { min: 30, default: 30 }
  });
  const viewerPane = createPaneSize(() => frameRef, {
    min: 60,
    fallback: { min: 40 }
  });

  const monitorsPane = createPaneSize(() => frameRef, {
    min: 28,
    default: 28,
    max: 28,
    fallback: { min: 15, max: 15 }
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
  <main class="h-screen w-screen text-fg">
    <Sidebar.Provider class="h-full min-h-0 overflow-hidden">
      <Sidebar.Root
        collapsible="none"
        class="w-56 shrink-0 overflow-hidden border-r border-line"
        role="navigation"
        aria-label="Instrument navigation"
      >
        <Sidebar.Header class="h-pane-header shrink-0 justify-center py-0">
          <StationMenu
            {stationId}
            {stationName}
            selectedInstrumentId={selectedInstrumentId || app.activeName}
            disabled={instrumentTransition}
            onselectinstrument={selectInstrument}
            onclose={showCloseDialog}
            onsettings={showSettings}
            ondashboard={showDashboard}
          />
        </Sidebar.Header>
        <Sidebar.Content>
          <InstrumentNavigation instrumentId={selectedInstrumentId || app.activeName || undefined} />
        </Sidebar.Content>
        {#if app.instrument}
          <Sidebar.Footer class="flex-row gap-1 border-t border-line-muted bg-element-bg/40 p-2">
            {#each ['undo', 'redo'] as const as action (action)}
              {@const label = action === 'undo' ? 'Undo' : 'Redo'}
              {@const edit = app.instrument.history[`${action}_label`]}
              {@const title = edit === null ? `Nothing to ${action}` : `${label}: ${edit}`}
              <span class="min-w-0 flex-1" {title}>
                <Button
                  variant="ghost"
                  size="sm"
                  class="w-full text-base disabled:opacity-40"
                  aria-label={title}
                  disabled={!canReplayHistory || edit === null}
                  onclick={() => replayHistory(action)}
                >
                  {#if action === 'undo'}
                    <Undo />
                  {:else}
                    <Redo />
                  {/if}
                  {label}
                </Button>
              </span>
            {/each}
          </Sidebar.Footer>
        {:else if instrumentId && app.stationStatus !== 'closing'}
          <Sidebar.Footer class="gap-1 border-t border-line-muted bg-element-bg/40 p-2">
            <Button
              variant="default"
              size="sm"
              class="justify-start text-base font-normal"
              title={openInstrumentTitle}
              disabled={!canOpenInstrument}
              onclick={openInstrument}
            >
              {#if instrumentTransition}
                <Spinner class="size-3.5" />
                <span>Opening instrument…</span>
              {:else}
                <Power />
                <span>Open instrument</span>
              {/if}
            </Button>
          </Sidebar.Footer>
        {/if}
      </Sidebar.Root>
      <PaneGroup
        direction="horizontal"
        bind:ref={frameRef}
        autoSaveId="shell:frame"
        class="h-full min-w-0 flex-1 bg-surface text-fg"
      >
        <Pane {...contentPane} class="grid min-w-0 grid-rows-[minmax(0,1fr)]">
          <div class="flex min-h-0 min-w-0 flex-col overflow-hidden bg-canvas">
            {@render children()}
          </div>
        </Pane>
        <PaneDivider direction="vertical" />
        <Pane {...viewerPane} class="grid min-w-0 grid-rows-[minmax(0,1fr)]">
          <div class="flex min-h-0 min-w-0 flex-col overflow-hidden">
            <CenterPane />
          </div>
        </Pane>
        {#if app.instrument}
          <PaneDivider direction="vertical" />
          <Pane {...monitorsPane} class="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
            <MonitorsPane instrument={app.instrument} />
          </Pane>
        {/if}
      </PaneGroup>
    </Sidebar.Provider>
  </main>
  <Dialog.Root bind:open={closeDialogOpen}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>
          {pendingSwitch ? 'Switch instrument?' : 'Close instrument?'}
        </Dialog.Title>
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
          {closingInstrument ? 'Closing…' : pendingSwitch ? 'Close and switch' : 'Close instrument'}
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
