<script lang="ts">
  import './layout.css';

  import { createHotkey, createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { Accordion, DropdownMenu } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { PersistedState, useEventListener } from 'runed';
  import type { Component } from 'svelte';
  import { onDestroy, onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import favicon from '$lib/assets/favicon.svg';
  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import { GridCanvas } from '$lib/grid';
  import { provideTaskSelection } from '$lib/grid/selection.svelte';
  import { ChevronDown, Crosshair, Layers, Microscope, TuneVertical, WaveformsIcon } from '$lib/icons';
  import { Button, Dialog, Toaster } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import MetadataPanel from '$lib/MetadataPanel.svelte';
  import { setVoxelApp, VoxelApp } from '$lib/model';
  import { PreviewCanvas } from '$lib/preview';
  import ProfileSelector from '$lib/ProfileSelector.svelte';
  import StartAcquisition from '$lib/StartAcquisition.svelte';
  import StencilControls from '$lib/StencilControls.svelte';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { cn, createPaneSize, toastError } from '$lib/utils';
  import VoxelLogo from '$lib/VoxelLogo.svelte';

  import ConnectionSplash from './ConnectionSplash.svelte';
  import LaunchScreen from './LaunchScreen.svelte';

  const { children } = $props();

  const app = new VoxelApp();
  setVoxelApp(app);
  provideTaskSelection();

  onMount(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
    toastError(app.initialize());
  });
  onDestroy(() => app.dispose());
  useEventListener(window, 'beforeunload', () => app.dispose());

  const logs = $derived(app.logs);

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
  const leftPane = createPaneSize(() => shellRef, { min: 740, fallbackMin: 30 });
  const rightPane = createPaneSize(() => shellRef, { min: 336, max: 350, fallbackMin: 15, fallbackMax: 18 });

  const navTabs: { id: Pathname; label: string; icon: Component }[] = [
    { id: '/', label: 'Inspect', icon: Microscope },
    { id: '/snap', label: 'Snap', icon: Crosshair },
    { id: '/tune', label: 'Tune', icon: WaveformsIcon },
    { id: '/configure', label: 'Configure', icon: TuneVertical },
    { id: '/plan', label: 'Plan', icon: Layers }
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

  // Sidebar accordion: multiple sections may be open; Grid Stencil open by default.
  let openSections = $state<string[]>(['grid']);
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{#if !app.client.isConnected}
  <ConnectionSplash {app} />
{:else if !app.instrument}
  <LaunchScreen {app} />
{:else}
  {@const instrument = app.instrument}
  {@const isPreviewing = instrument.mode === 'preview'}
  {@const isAcquiring = instrument.mode === 'capture'}
  <div bind:this={shellRef} class="h-screen w-full text-fg">
    <PaneGroup direction="horizontal" autoSaveId="shell.v2">
      <Pane defaultSize={leftPane.minSize} minSize={leftPane.minSize} maxSize={60}>
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
                      disabled={!app.instrument}
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
                if (isAcquiring) toastError(instrument.stopAcquisition());
                else if (isPreviewing) instrument.preview.stopPreview();
                else instrument.preview.startPreview();
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
              {#if bottomPanelTab === 'logs'}
                <LogViewer {logs} class="bg-card" />
              {/if}
            </Pane>
          </PaneGroup>

          <!-- Footer: close session + tab strip + profile selector -->
          <footer class="flex h-12 items-center justify-between gap-20 border-t border-border px-4 py-2">
            <div class="flex items-center gap-2">
              <div class="flex divide-x divide-border rounded border border-border">
                <button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
              </div>
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
              <PreviewCanvas previewer={instrument.preview} fov={instrument.fov} />
            </Pane>
            <PaneDivider direction="horizontal" />
            <Pane defaultSize={50} minSize={30} class="h-full flex-1">
              <GridCanvas {instrument} />
            </Pane>
          </PaneGroup>
        </main>
      </Pane>
      <PaneDivider direction="vertical" />
      <Pane defaultSize={16} {...rightPane} class="flex flex-col">
        <div class="flex h-15 shrink-0 items-center border-b border-border px-3">
          <ProfileSelector {instrument} size="md" class="w-full" />
        </div>
        <div class="flex flex-1 flex-col divide-y divide-border overflow-y-auto">
          {#if instrument.cameras.size > 0}
            <CamerasMonitor {instrument} />
          {/if}
          {#if instrument.lasers.size > 0}
            <LasersMonitor {instrument} />
          {/if}
          <div class="flex-1"></div>
          {#snippet section(id: string, title: string, body: import('svelte').Snippet)}
            <Accordion.Item value={id}>
              <Accordion.Header>
                <Accordion.Trigger
                  class="flex w-full cursor-pointer items-center justify-between gap-2 p-3 text-fg-muted/70 uppercase transition-colors outline-none hover:text-fg-muted [&[data-state=closed]>svg]:-rotate-90"
                >
                  <span class="text-xs font-medium tracking-wide">{title}</span>
                  <ChevronDown class="h-3.5 w-3.5 shrink-0 transition-transform duration-200" />
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Content
                class="overflow-hidden data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down"
              >
                <div class="px-3 pb-3">{@render body()}</div>
              </Accordion.Content>
            </Accordion.Item>
          {/snippet}

          {#snippet gridBody()}<StencilControls {instrument} />{/snippet}
          {#snippet metadataBody()}<MetadataPanel {instrument} />{/snippet}
          <Accordion.Root type="multiple" bind:value={openSections}>
            {@render section('grid', 'Grid Stencil', gridBody)}
            {@render section('metadata', 'Metadata', metadataBody)}
          </Accordion.Root>
        </div>
        <StartAcquisition {app} class="shrink-0 border-t border-border" />
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
<Toaster position="bottom-left" />
