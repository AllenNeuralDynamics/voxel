<script lang="ts">
  import './layout.css';

  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { Pane, PaneGroup } from 'paneforge';
  import { useEventListener, watch } from 'runed';
  import type { Component } from 'svelte';
  import { onDestroy, onMount } from 'svelte';
  import { fade } from 'svelte/transition';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import favicon from '$lib/assets/favicon.svg';
  import DefaultConfigDialog from '$lib/DefaultConfigDialog.svelte';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import RoutingMonitor from '$lib/devices/RoutingMonitor.svelte';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import {
    ChevronDown,
    ChevronUp,
    DotsSpinner,
    ImageLight,
    Layers,
    Microscope,
    PanelRight,
    TuneVertical,
    WaveformsIcon
  } from '$lib/icons';
  import { Button, Dialog, Toaster } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { type PreviewMode, setVoxelApp, VoxelApp } from '$lib/model';
  import PreviewCanvas from '$lib/preview/PreviewCanvas.svelte';
  import SnapshotFlyOverlay from '$lib/preview/SnapshotFlyOverlay.svelte';
  import ProfileSelector from '$lib/ProfileSelector.svelte';
  import RunButton from '$lib/RunButton.svelte';
  import { provideStageScene, StageLayersSidebar, StageView, type StageViewport } from '$lib/stage';
  import StageGizmo from '$lib/stage/StageGizmo.svelte';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { cn, createPaneSize, pref, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import ConnectionSplash from './ConnectionSplash.svelte';

  const { children } = $props();

  const app = new VoxelApp();
  setVoxelApp(app);
  provideTaskSelection();
  provideStageScene();
  let stageViewport = $state.raw<StageViewport>({ mode: 'auto' });
  const stageLayersCollapsed = pref('stage:sidebar-collapsed', false);

  async function configureServiceWorker(): Promise<void> {
    if (!('serviceWorker' in navigator)) return;
    if (import.meta.env.DEV) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      return;
    }
    await navigator.serviceWorker.register('/sw.js');
  }

  onMount(() => {
    toastError(configureServiceWorker());
    toastError(app.initialize());
  });
  onDestroy(() => app.dispose());
  useEventListener(window, 'beforeunload', () => app.dispose());

  const logs = $derived(app.logs);
  const logWarnings = $derived(logs.filter((log) => log.level === 'warning').length);
  const logErrors = $derived(logs.filter((log) => log.level === 'error').length);

  // --- Keyboard shortcuts ---

  createHotkey('Alt+P', () => {
    const inst = app.instrument;
    if (!inst) return;
    if (inst.mode === 'preview') inst.preview.stopPreview();
    else inst.preview.startPreview();
  });
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (app.instrument) closeDialogOpen = true;
  });

  // --- Shell nav ---

  let shellRef = $state<HTMLElement | null>(null);

  type Segment = { key: string; label: string; icon?: Component; active: boolean; select: () => void };

  const navTabs: { id: Pathname; label: string; icon: Component }[] = [
    { id: '/inspect', label: 'Inspect', icon: Microscope },
    { id: '/sync', label: 'Sync', icon: WaveformsIcon },
    { id: '/configure', label: 'Configure', icon: TuneVertical },
    { id: '/plan', label: 'Plan', icon: Layers }
  ];

  const previewModes: { mode: PreviewMode; label: string }[] = [
    { mode: 'live', label: 'Live' },
    { mode: 'stage', label: 'Stage' }
  ];

  const viewId = $derived<Pathname>(
    navTabs.find((t) => t.id !== '/' && page.url.pathname.startsWith(t.id))?.id ??
      (page.url.pathname === '/debug' ? '/debug' : '/')
  );

  watch(
    () => app.instrument,
    () => {
      if (!app.instrument && viewId !== '/') goto(resolve('/'), { replaceState: true });
    }
  );

  function selectView(id: Pathname) {
    if (viewId === id) return;
    goto(resolve(id), { keepFocus: true, noScroll: true });
  }

  const navSegments = $derived<Segment[]>(
    navTabs.map((t) => ({
      key: t.id,
      label: t.label,
      icon: t.icon,
      active: viewId === t.id,
      select: () => selectView(t.id)
    }))
  );

  const modeSegments = $derived<Segment[]>(
    previewModes.map((m) => ({
      key: m.mode,
      label: m.label,
      active: app.viewMode.get() === m.mode,
      select: () => app.viewMode.set(m.mode)
    }))
  );

  // Pane sizes

  let workspaceSplitEl = $state<HTMLElement | null>(null);
  const contentPane = createPaneSize(() => workspaceSplitEl, {
    min: 42,
    default: 42,
    max: 64,
    fallback: { min: 30, default: 30, max: 50 }
  });
  const monitorsPane = createPaneSize(() => shellRef, {
    min: 24,
    default: 30,
    max: 30,
    fallback: { min: 15, max: 18 }
  });

  // Vertical split inside the monitors pane: telemetry (top) over the stage gizmo (bottom).
  let monitorsSplitEl = $state<HTMLElement | null>(null);
  const gizmoPane = createPaneSize(() => monitorsSplitEl, {
    default: 22,
    min: 18,
    max: 28,
    fallback: { min: 28, max: 40, default: 32 }
  });

  let logsPaneRef = $state<Pane | undefined>(undefined);
  const logsOpen = $derived(logsPaneRef ? !logsPaneRef.isCollapsed() : false);

  function toggleLogs() {
    if (logsPaneRef?.isCollapsed()) logsPaneRef.expand();
    else logsPaneRef?.collapse();
  }

  // --- Dialog state ---

  let closeDialogOpen = $state(false);
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{#if !app.client.isConnected}
  <ConnectionSplash {app} />
{:else}
  {#snippet segmented(segments: Segment[])}
    <div class="flex h-ui-md items-center rounded-md border border-input bg-canvas/50 p-0.5">
      {#each segments as { key, label, icon: Icon, active, select } (key)}
        <button
          type="button"
          title={label}
          onclick={select}
          class={cn(
            'inline-flex h-full min-w-20 cursor-pointer items-center justify-center gap-1.5 rounded-sm px-4 text-lg whitespace-nowrap transition-colors',
            active ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
          )}
        >
          {#if Icon}
            <Icon width="12" height="12" class="shrink-0" />
          {/if}
          {label}
        </button>
      {/each}
    </div>
  {/snippet}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell:frame">
      <!-- Main workspace: routed content beside the viewer/log surface. -->
      <Pane>
        <PaneGroup direction="horizontal" bind:ref={workspaceSplitEl} autoSaveId="shell:workspace">
          <Pane {...contentPane} class="grid h-full grid-rows-[auto_1fr] bg-surface">
            <header class="flex h-15 shrink-0 items-center gap-x-5 border-b border-border bg-elevated px-4">
              <a
                href={resolve('/')}
                class={cn(
                  'flex shrink-0 items-center transition-colors',
                  viewId === '/' ? 'text-fg' : 'text-fg-muted hover:text-fg'
                )}
                title="Home"
                aria-label="Home"
              >
                <VoxelLogo class="size-ui-md" />
              </a>
              {#if app.instrument}
                <nav class="flex items-center">
                  {@render segmented(navSegments)}
                </nav>
              {/if}
            </header>
            <div class="flex h-full min-h-0 min-w-0 flex-col">
              {@render children()}
            </div>
          </Pane>
          <PaneDivider direction="vertical" />

          {#if app.instrument}
            {@const instrument = app.instrument}
            <!-- Viewer: Preview + Logs (centerpiece) -->
            <Pane class="flex h-full flex-col bg-canvas">
              <main class="min-h-0 flex-1 overflow-hidden">
                <PaneGroup direction="vertical" autoSaveId="shell:workspace:viewer">
                  <Pane defaultSize={65} minSize={30} class="flex flex-1 flex-col justify-center">
                    <div class="flex h-full flex-col bg-canvas">
                      <div class="relative flex min-h-0 flex-1">
                        <div
                          class="pointer-events-none absolute inset-x-3 top-3 z-20 flex items-center justify-between"
                        >
                          <div class="pointer-events-auto">
                            {@render segmented(modeSegments)}
                          </div>
                          <div class="pointer-events-auto flex items-center gap-2">
                            <Button
                              variant="secondary"
                              size="md"
                              disabled={app.snapping}
                              title={app.snapping ? 'Snapping…' : 'Capture snapshot'}
                              class="border-border bg-elevated text-lg shadow-sm"
                              onclick={() => toastError(app.captureSnapshot())}
                            >
                              {#if app.snapping}
                                <DotsSpinner width="16" height="16" />
                              {:else}
                                <ImageLight width="16" height="16" />
                              {/if}
                              Snap
                            </Button>
                            <Button
                              variant="secondary"
                              size="icon-lg"
                              aria-expanded={!stageLayersCollapsed.get()}
                              title={stageLayersCollapsed.get() ? 'Show layers' : 'Hide layers'}
                              class="border-border bg-elevated shadow-sm"
                              onclick={() => stageLayersCollapsed.set(!stageLayersCollapsed.get())}
                            >
                              <PanelRight width="22" height="22" />
                            </Button>
                          </div>
                        </div>
                        <div class="relative min-w-0 flex-1 overflow-hidden" data-fly-origin>
                          {#if app.viewMode.get() === 'stage'}
                            <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
                              <StageView bind:viewport={stageViewport} />
                            </div>
                          {:else}
                            <div class="absolute inset-0" transition:fade={{ duration: 120 }}>
                              <PreviewCanvas previewer={instrument.preview} fov={instrument.fov} />
                            </div>
                          {/if}
                        </div>
                        <StageLayersSidebar collapsed={stageLayersCollapsed.get()} />
                      </div>

                      <SnapshotFlyOverlay />
                    </div>
                  </Pane>
                  <PaneDivider direction="horizontal" ondblclick={toggleLogs} />
                  <Pane
                    bind:this={logsPaneRef}
                    collapsible
                    collapsedSize={0}
                    defaultSize={35}
                    minSize={20}
                    maxSize={55}
                    class="bg-surface"
                  >
                    <LogViewer {logs} class="bg-canvas/35" />
                  </Pane>
                </PaneGroup>
              </main>
              <footer class="flex h-8 shrink-0 border-t border-border bg-elevated">
                <button
                  type="button"
                  aria-expanded={logsOpen}
                  onclick={toggleLogs}
                  class="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 text-base text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                >
                  <span class="font-medium text-fg">Logs</span>
                  {#if logErrors > 0}
                    <span class="text-danger">{logErrors} {logErrors === 1 ? 'error' : 'errors'}</span>
                  {/if}
                  {#if logWarnings > 0}
                    <span class="text-warning">{logWarnings} {logWarnings === 1 ? 'warning' : 'warnings'}</span>
                  {/if}
                  <span class="ml-auto">{logsOpen ? 'Collapse' : 'Expand'}</span>
                  {#if logsOpen}
                    <ChevronDown width="14" height="14" />
                  {:else}
                    <ChevronUp width="14" height="14" />
                  {/if}
                </button>
              </footer>
            </Pane>
          {:else}
            <Pane class="min-h-0 min-w-0 bg-canvas">
              <LogViewer logs={app.logs} />
            </Pane>
          {/if}
        </PaneGroup>
      </Pane>

      {#if app.instrument}
        {@const instrument = app.instrument}
        <PaneDivider direction="vertical" />

        <!-- Monitors: run controls + device telemetry -->
        <Pane {...monitorsPane} class="flex flex-col bg-surface">
          <header class="flex shrink-0 flex-col gap-3 border-b border-border bg-elevated px-4 py-3">
            <RunButton {app} class="w-full justify-center" />
            <ProfileSelector {instrument} size="md" class="w-full" />
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
  </div>

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
{/if}

<AppearanceSheet bind:open={themes.pickerOpen} />
<DefaultConfigDialog />
<Toaster position="bottom-left" />
