<script lang="ts">
  import './layout.css';
  import favicon from '$lib/assets/favicon.svg';
  import type { Component } from 'svelte';
  import { onMount, onDestroy } from 'svelte';
  import { useEventListener, PersistedState } from 'runed';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import type { Pathname } from '$app/types';
  import { Pane, PaneGroup } from 'paneforge';
  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { App } from '$lib/app';
  import { Toaster, Dialog, Button } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { cn, createPaneMinSize } from '$lib/utils';
  import { setSessionContext, setLogsContext } from '$lib/context';
  import { Power, Crosshair, Layers, Play } from '$lib/icons';
  import VoxelLogo from '$lib/VoxelLogo.svelte';
  import StartButton from '$lib/StartButton.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import LasersPanel from '$lib/device/LasersPanel.svelte';
  import CamerasPanel from '$lib/device/CamerasPanel.svelte';
  import AuxDevicesPanel from '$lib/device/AuxDevicesPanel.svelte';
  import ProfileWaveforms from '$lib/profile/ProfileWaveforms.svelte';
  import { ProfileSelector } from '$lib/profile';
  import { PreviewCanvas } from '$lib/preview';
  import { GridCanvas } from '$lib/grid';
  import { AppearanceSheet, themes } from '$lib/themes';
  import LaunchScreen from './LaunchScreen.svelte';
  import ConnectionSplash from './ConnectionSplash.svelte';
  import { lastInstrumentPath } from './(instrument)/+layout.svelte';

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
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
  createHotkeySequence(['Mod+K', 'Q'], () => {
    if (session) closeDialogOpen = true;
  });

  // --- Shell nav ---

  let shellRef = $state<HTMLElement | null>(null);
  const leftPaneMin = createPaneMinSize(() => shellRef, 850, 50);

  const navTabs: { id: Pathname; label: string; icon: Component }[] = [
    { id: '/scout', label: 'Scout', icon: Crosshair },
    { id: '/plan', label: 'Plan', icon: Layers },
    { id: '/acquisition', label: 'Acquire', icon: Play }
  ];

  const viewId = $derived<Pathname>(
    navTabs.find((t) => t.id !== '/' && page.url.pathname.startsWith(t.id))?.id ??
      (page.url.pathname === '/debug' ? '/debug' : '/')
  );

  function gotoView(id: Pathname) {
    goto(resolve(id), { keepFocus: true, noScroll: true });
  }

  function selectView(id: Pathname) {
    if (viewId === id) return;
    if (id === '/' && lastInstrumentPath && lastInstrumentPath !== '/') {
      goto(resolve(lastInstrumentPath as '/'), { keepFocus: true, noScroll: true });
    } else {
      gotoView(id);
    }
  }

  // --- Bottom pane (setup) ---

  const panelTab = new PersistedState('setup.panel.tab', 'lasers');
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

{#if app.client.connectionState !== 'connected' || !app.status || (app.hasSession && !session)}
  <ConnectionSplash {app} />
{:else if session}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell">
      <Pane defaultSize={60} minSize={leftPaneMin.value} maxSize={70}>
        <div class="grid h-full grid-rows-[auto_1fr_auto]">
          <!-- Header: logo + nav tabs + StartButton -->
          <header
            class="grid grid-cols-[auto_auto_1fr] items-center gap-x-4 border-b border-border bg-elevated px-4 py-4"
          >
            <button
              onclick={() => selectView('/')}
              title="Instrument"
              class="flex cursor-pointer items-center text-fg-muted transition-colors hover:text-fg"
            >
              <VoxelLogo class="size-ui-sm" />
            </button>

            <div class="col-start-3 flex items-center justify-end gap-4">
              <StartButton {session} />
            </div>

            <nav
              class="col-start-2 row-start-1 grid w-fit grid-cols-3 divide-x divide-fg-faint/60 overflow-hidden rounded-lg border border-fg-faint/60"
            >
              {#each navTabs as tab (tab.id)}
                {@const Icon = tab.icon}
                <button
                  onclick={() => selectView(tab.id)}
                  class={cn(
                    'flex h-ui-md items-center justify-center gap-2 px-4 text-sm transition-colors',
                    viewId === tab.id
                      ? 'bg-element-selected text-fg'
                      : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                  )}
                  title={tab.label}
                >
                  <Icon width="12" height="12" class="shrink-0" />
                  {tab.label}
                </button>
              {/each}
            </nav>
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
            >
              {#if bottomPanelTab === 'devices'}
                <AuxDevicesPanel {session} class="h-full overflow-auto p-2" />
              {:else if bottomPanelTab === 'cameras'}
                <CamerasPanel {session} class="h-full overflow-auto p-4" />
              {:else if bottomPanelTab === 'lasers'}
                <LasersPanel {session} />
              {:else if bottomPanelTab === 'waveforms'}
                {#if session.profiles.activeId}
                  <ProfileWaveforms
                    profiles={session.profiles}
                    devices={session.devices}
                    rigCfg={session.rig_cfg}
                    acquiring={session.mode === 'acquiring'}
                    profileId={session.profiles.activeId}
                    class="h-full overflow-auto p-2"
                  />
                {:else}
                  <div class="flex h-full items-center justify-center text-sm text-fg-muted">
                    Select a profile to view waveforms
                  </div>
                {/if}
              {:else if bottomPanelTab === 'logs'}
                <div class="h-full overflow-hidden bg-card p-2">
                  <LogViewer {logs} onClear={clearLogs} />
                </div>
              {/if}
            </Pane>
          </PaneGroup>

          <!-- Footer: close session + tab strip + profile selector -->
          <footer class="flex h-ui-xl items-center justify-between gap-20 border-t border-border px-4 py-2">
            <div class="flex items-center gap-2">
              <button
                type="button"
                title="Close Session (⌘K Q)"
                onclick={() => (closeDialogOpen = true)}
                class="-ml-2 flex h-ui-xs items-center justify-center rounded px-2 text-fg-muted transition-colors hover:bg-danger/10 hover:text-danger"
              >
                <Power width="16" height="16" />
              </button>
              <div class="flex divide-x divide-border rounded border border-border">
                <button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
                <button onclick={() => selectTab('waveforms')} class={tabClass(bottomPanelTab === 'waveforms')}
                  >Waveforms</button
                >
                <button onclick={() => selectTab('devices')} class={tabClass(bottomPanelTab === 'devices')}
                  >Auxiliary</button
                >
                <button onclick={() => selectTab('cameras')} class={tabClass(bottomPanelTab === 'cameras')}>Cameras</button>
                <button onclick={() => selectTab('lasers')} class={tabClass(bottomPanelTab === 'lasers')}>
                  Lasers
                  {#each Object.values(session.lasers) as laser (laser.deviceId)}
                    <div class="relative">
                      {#if laser.isEnabled}
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
              <ProfileSelector profiles={session.profiles} stacks={session.stacks} size="xs" class="w-full" />
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
