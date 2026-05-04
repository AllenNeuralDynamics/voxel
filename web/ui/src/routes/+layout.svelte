<script lang="ts">
  import './layout.css';

  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { DropdownMenu } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { PersistedState, useEventListener } from 'runed';
  import type { Component } from 'svelte';
  import { onDestroy, onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import { App } from '$lib/app.svelte';
  import favicon from '$lib/assets/favicon.svg';
  import { setLogsContext, setSessionContext } from '$lib/context';
  import { GridCanvas } from '$lib/grid';
  import { Crosshair, Layers, Microscope, Play, TuneVertical, WaveformsIcon } from '$lib/icons';
  import { Button, Dialog, Toaster } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { ProfileSelector } from '$lib/microscope';
  import AuxDevicesPanel from '$lib/microscope/AuxDevicesPanel.svelte';
  import LasersPanel from '$lib/microscope/LasersPanel.svelte';
  import { PreviewCanvas } from '$lib/preview';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { cn, createPaneMinSize } from '$lib/utils';

  import ConnectionSplash from './ConnectionSplash.svelte';
  import LaunchScreen from './LaunchScreen.svelte';
  import LogViewer from './LogViewer.svelte';
  import VoxelLogo from './VoxelLogo.svelte';

  let { children } = $props();

  // --- App lifecycle ---

  const app = new App();

  function cleanup() {
    app.dispose();
  }

  useEventListener(window, 'beforeunload', cleanup);

  onMount(async () => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js');
    }
    try {
      await app.initialize();
    } catch {
      // Connection state managed by client — splash handles the UI
    }
  });

  onDestroy(cleanup);

  const session = $derived(app.session);
  const logs = $derived(app.logs);
  const clearLogs = () => app.clearLogs();

  // --- Session-scoped context (consumers only dereference when session is truthy) ---

  setSessionContext(() => session!);
  setLogsContext({
    get logs() {
      return app.logs;
    },
    clearLogs: () => app.clearLogs()
  });

  // --- Keyboard shortcuts ---

  createHotkey('Mod+Z', () => session?.undo.undo());
  createHotkey('Mod+Shift+Z', () => session?.undo.redo());
  createHotkey('Alt+P', () => {
    if (!session) return;
    if (session.mode === 'previewing') session.preview.stopPreview();
    else session.preview.startPreview();
  });
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (session) closeDialogOpen = true;
  });

  // --- Shell nav ---

  let shellRef = $state<HTMLElement | null>(null);
  const leftPaneMin = createPaneMinSize(() => shellRef, 870, 50);

  const navTabs: { id: Pathname; label: string; icon: Component }[] = [
    { id: '/', label: 'Inspect', icon: Microscope },
    { id: '/tune', label: 'Tune', icon: WaveformsIcon },
    { id: '/configure', label: 'Configure', icon: TuneVertical },
    { id: '/snap', label: 'Snap', icon: Crosshair },
    { id: '/plan', label: 'Plan', icon: Layers },
    { id: '/acquire', label: 'Acquire', icon: Play }
  ];

  const viewId = $derived<Pathname>(
    navTabs.find((t) => t.id !== '/' && page.url.pathname.startsWith(t.id))?.id ??
      (page.url.pathname === '/debug' ? '/debug' : '/')
  );

  function selectView(id: Pathname) {
    if (viewId === id) return;
    goto(resolve(id), { keepFocus: true, noScroll: true });
  }

  // --- Bottom pane (setup) ---

  const panelTab = new PersistedState('setup.panel.tab', 'logs');
  let bottomPanelTab = $derived(panelTab.current);

  function setTab(tab: string) {
    panelTab.current = tab;
  }
  let bottomPane: Pane | undefined = $state(undefined);

  function selectTab(id: string) {
    if (bottomPanelTab === id) {
      if (bottomPane?.isCollapsed()) bottomPane.expand();
      else bottomPane?.collapse();
    } else {
      setTab(id);
      if (bottomPane?.isCollapsed()) bottomPane.expand();
    }
  }

  function tabClass(selected: boolean): string {
    return cn(
      'gap-2 flex items-center h-ui-xs px-2 text-sm transition-colors hover:bg-element-hover',
      selected ? 'bg-element-bg text-fg' : 'text-fg-muted'
    );
  }

  // --- Dialog state ---

  let closeDialogOpen = $state(false);
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{#if app.client.state !== 'connected' || !app.status || (app.hasSession && !session)}
  <ConnectionSplash {app} />
{:else if session}
  {@const isPreviewing = session.mode === 'previewing'}
  {@const isAcquiring = session.mode === 'acquiring'}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell">
      <Pane defaultSize={60} minSize={leftPaneMin.value} maxSize={70}>
        <div class="grid h-full grid-rows-[auto_1fr_auto]">
          <header class="flex h-15 items-center justify-between border-b border-border bg-surface px-4">
            <div class="flex items-center gap-x-3">
              <DropdownMenu.Root>
                <DropdownMenu.Trigger
                  class="flex cursor-pointer items-center text-fg-muted transition-colors hover:text-fg"
                  title="App menu"
                >
                  <VoxelLogo class="size-ui-md" />
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    align="start"
                    sideOffset={8}
                    class="z-50 min-w-56 rounded-md border border-border bg-elevated p-1 text-sm shadow-lg outline-none"
                  >
                    <DropdownMenu.Item
                      class="flex cursor-pointer items-center rounded px-2 py-1.5 outline-none hover:bg-element-hover focus:bg-element-hover data-highlighted:bg-element-hover"
                      onclick={() => (themes.pickerOpen = true)}
                    >
                      Change Appearance
                      <span class="ml-8 text-xs text-fg-faint">⌘K T</span>
                    </DropdownMenu.Item>
                    <DropdownMenu.Separator class="my-1 h-px bg-border" />
                    <DropdownMenu.Item
                      class="flex cursor-pointer items-center rounded px-2 py-1.5 outline-none hover:bg-element-hover focus:bg-element-hover data-disabled:cursor-not-allowed data-disabled:opacity-50 data-highlighted:bg-element-hover"
                      disabled={!session}
                      onclick={() => (closeDialogOpen = true)}
                    >
                      Close Session…
                      <span class="ml-8 text-xs text-fg-faint">⌘K Q</span>
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>

              <nav class="flex h-ui-md items-center gap-x-1 text-fg-muted">
                {#each navTabs as tab (tab.id)}
                  {@const Icon = tab.icon}
                  {@const active = viewId === tab.id}
                  <button
                    onclick={() => selectView(tab.id)}
                    class={cn(
                      'inline-flex h-full cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm whitespace-nowrap transition-colors',
                      active
                        ? 'border-fg-accent/30 bg-fg-accent/10 text-fg'
                        : 'border-transparent hover:bg-element-hover hover:text-fg'
                    )}
                    title={tab.label}
                  >
                    <Icon width="12" height="12" class="shrink-0" />
                    {tab.label}
                  </button>
                {/each}
              </nav>
            </div>

            <Button
              class="min-w-38"
              variant={isPreviewing || isAcquiring ? 'danger' : 'success'}
              size="lg"
              onclick={() => {
                if (isAcquiring) session.acquisition.stop();
                else if (isPreviewing) session.preview.stopPreview();
                else session.preview.startPreview();
              }}
            >
              {#if isAcquiring}
                Stop Acquisition
              {:else if isPreviewing}
                Stop Preview
              {:else}
                Start Preview
              {/if}
            </Button>
          </header>

          <!-- Middle: children + bottom pane -->
          <PaneGroup direction="vertical" autoSaveId="setup.layout">
            <Pane>
              <div class="flex h-full flex-col">
                {@render children()}
              </div>
            </Pane>
            <PaneDivider
              direction="horizontal"
              ondblclick={() => {
                if (bottomPane?.isCollapsed()) bottomPane.expand();
                else bottomPane?.collapse();
              }}
            />
            <Pane
              bind:this={bottomPane}
              collapsible
              collapsedSize={0}
              defaultSize={40}
              minSize={30}
              maxSize={50}
              onCollapse={() => {}}
              class="bg-surface/50"
            >
              {#if bottomPanelTab === 'devices'}
                <AuxDevicesPanel microscope={session.scope} class="h-full overflow-auto p-4" />
              {:else if bottomPanelTab === 'lasers'}
                <LasersPanel microscope={session.scope} />
                <!-- {:else if bottomPanelTab === 'analog-out'}
                {#if session.scope.profiles.activeId}
                  <AnalogOutPanel
                    microscope={session.scope}
                    canEdit={session.mode === 'idle'}
                    class="h-full overflow-auto"
                  />
                {:else}
                  <div class="flex h-full items-center justify-center text-sm text-fg-muted">
                    Select a profile to view waveforms
                  </div>
                {/if} -->
              {:else if bottomPanelTab === 'logs'}
                <div class="h-full overflow-hidden bg-card p-4 pt-2">
                  <LogViewer {logs} onClear={clearLogs} />
                </div>
              {/if}
            </Pane>
          </PaneGroup>

          <!-- Footer: close session + tab strip + profile selector -->
          <footer class="flex h-12 items-center justify-between gap-20 border-t border-border px-4 py-2">
            <div class="flex items-center gap-2">
              <div class="flex divide-x divide-border rounded border border-border">
                <button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
                <!-- <button onclick={() => selectTab('analog-out')} class={tabClass(bottomPanelTab === 'analog-out')}
                  >Analog Out</button
                > -->
                <button onclick={() => selectTab('devices')} class={tabClass(bottomPanelTab === 'devices')}>
                  Auxiliary
                </button>
                <button onclick={() => selectTab('lasers')} class={tabClass(bottomPanelTab === 'lasers')}>
                  Lasers
                  {#each [...session.scope.lasers.values()] as laser (laser.id)}
                    {@const enabled = laser.isEnabled?.value === true}
                    <div class="relative">
                      {#if enabled}
                        <div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>
                        <span
                          class="absolute inset-0 animate-ping rounded-full opacity-75"
                          style="background-color: {laser.color};"
                        ></span>
                      {:else}
                        <div class="h-2 w-2 rounded-full border opacity-70" style="border-color: {laser.color};"></div>
                      {/if}
                    </div>
                  {/each}
                </button>
              </div>
            </div>
            <div class="max-w-100 min-w-40 flex-1">
              <ProfileSelector profiles={session.scope.profiles} stacks={session.stacks} size="md" class="w-full" />
            </div>
          </footer>
        </div>
      </Pane>

      <PaneDivider direction="vertical" />

      <!-- Right column: Viewer (Preview + Grid Canvas) -->
      <Pane defaultSize={45}>
        <main class="flex h-full flex-col overflow-hidden">
          <PaneGroup direction="vertical" autoSaveId="shell.right">
            <Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center">
              <PreviewCanvas previewer={session.preview} fov={session.mosaic.fov} />
            </Pane>
            <PaneDivider direction="horizontal" />
            <Pane defaultSize={50} minSize={30} class="h-full flex-1">
              <GridCanvas {session} />
            </Pane>
          </PaneGroup>
        </main>
      </Pane>
    </PaneGroup>
  </div>

  <Dialog.Root bind:open={closeDialogOpen}>
    <Dialog.Content size="sm" showCloseButton={false}>
      <Dialog.Header>
        <Dialog.Title>Close Session</Dialog.Title>
      </Dialog.Header>
      <p class="text-sm text-fg-muted">
        Are you sure you want to close the current session? Any unsaved progress will be lost.
      </p>
      <Dialog.Footer>
        <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
        <Button
          variant="danger"
          onclick={() => {
            closeDialogOpen = false;
            app.closeSession();
          }}
        >
          Close Session
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{:else}
  <LaunchScreen {app} />
{/if}
<AppearanceSheet bind:open={themes.pickerOpen} />
<Toaster position="bottom-left" />
